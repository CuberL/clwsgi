#!/usr/bin/python
# -*- coding: utf-8 -*-

import gevent.monkey
gevent.monkey.patch_all()

import sys
import gevent
import urlparse
import socket
import logging
import logging.config

from os.path import abspath, dirname
_dir = dirname(abspath(__file__))

logging.config.fileConfig(_dir+"/logger.conf")
normal_logger = logging.getLogger("normal")
request_logger = logging.getLogger("request")

class Request(object):
    '''
    代表一个HTTP请求

    Args:
        app: 框架提供的application
        client: 一个连接了客户端（浏览器）的socket连接
        host: 服务器的主机名
        port: 服务器的端口
        addr: 客户端的地址，元组，分别是地址和端口
    '''
    def __init__(self, app, client, host, port, addr):
        self.response = client.makefile()
        self.request = client.makefile()
        self.client = client
        self.host = host
        self.port = port
        self.clientaddr = addr
        self.version = "HTTP/1.0"
        self.app = app
        self.serve()

    def start_response(self, status, response_headers, exc_info=None):
        """
        传入application的函数，用来启动一个HTTP回应

        Args:
            status: HTTP回应报文状态，比如`200 OK`
            response_headers: HTTP回应报头，列表类型，每个元素均为二元组
            exc_info: application提供的异常，可选

        Returns:
            一个write函数，可以让application自行写入报文，不过应尽量避免
        """
        response_header = ""
        response_header += self.version + " "
        response_header += status + '\r\n'
        for header in response_headers:
            response_header += '%s:%s\r\n'%(header[0], header[1])
        response_header += "\r\n"
        self.response.write(response_header)
        request_logger.info("", extra={
            "method": "GET",
            "ip": self.clientaddr[0],
            "path": self.env['PATH_INFO'] + (
                "?" + self.env['QUERY_STRING'] if not self.env['QUERY_STRING'] == ""
                else "")
            })
        return self.response.write

    def serve(self):
        """
        开始一个处理请求

        Raises:
            Exception: 捕获所有读取回应body时出现的错误并返回一个500错误
        """
        request_line = self.request.readline()
        method, path, version = request_line.split(' ')
        headers = {}
        self.request.readline()
        # 读取所有报文头
        while True:
            line = self.request.readline().strip()
            if line == "":
                break
            x = line.split(":")
            headers['HTTP_'+x[0].strip().upper().replace("-", "_")] = x[1].strip()
        # 获取URL Parse对象
        urlparsed = urlparse.urlparse(path)
        # 设置env字典
        env = {
            "REQUEST_METHOD": method,
            "SCRIPT_NAME": "",
            "PATH_INFO": urlparsed.path,
            "QUERY_STRING": urlparsed.query,
            "CONTENT_TYPE": headers['HTTP_CONTENT_TYPE'] if 'HTTP_CONTENT_TYPE' in headers else '',
            "CONTENT_LENGTH": headers['HTTP_CONTENT_LENGTH'] if 'HTTP_CONTENT_LENGTH' in headers else '',
            "SERVER_NAME": self.host,
            "SERVER_PORT": str(self.port),
            "SERVER_PROTOCOL": version,

            "wsgi.version": (1, 0),
            "wsgi.url_scheme": "http",
            "wsgi.input": self.request,
            "wsgi.errors": sys.stdout,
            "wsgi.multithread": False,
            "wsgi.multiprocess": False,
            "wsgi.run_once": False
        }
        env.update(headers)
        self.env = env
        # 调用application，传入env字典和start_response函数
        try:
            for part in self.app(env, self.start_response):
                self.response.write(part)
        except Exception, ex:
            print ex
            self.start_response("500 Internal Server Error", [('Content-Length', '5')])
            self.response.write("ERROR\r\n")
        finally:
            self.client.close()


class Server(object):
    """
    服务器对象
    
    Args:
        app: 框架提供的application
        host: 服务器端监听的地址
        port: 服务器端监听的端口
    """
    def __init__(self, app, host="0.0.0.0", port=6044):
        self.app = app
        self.host = host
        self.port = port
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((host, port))
        self.server.listen(1000)

    def handler(self, client, addr):
        """
        协程，启动一个Request

        Args:
            client: 连接客户端（服务器）的socket连接
            addr: 客户端的地址，二元组，包括地址和端口
        """
        Request(self.app, client, self.host, self.port, addr)

    def start(self):
        """
        启动服务器
        """
        normal_logger.info("Listening on %s:%s"%(self.host, self.port))
        while True:
            client, addr = self.server.accept()
            gevent.spawn(self.handler, client, addr)

if __name__ == '__main__':

    from flask import Flask

    application = Flask(__name__)

    @application.route('/hello', methods=["GET"])
    def hello():
        return "AC"

    server = Server(application)
    server.start()
