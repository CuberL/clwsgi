#!/usr/bin/python
# -*- coding: utf-8 -*-

import gevent.monkey
gevent.monkey.patch_all()

import sys
import gevent
import StringIO
import multiprocessing
import urlparse
import socket
import traceback
import logging
import logging.config

from os.path import abspath, dirname
_dir = dirname(abspath(__file__))

logging.config.fileConfig(_dir+"/logger.conf")
normal_logger = logging.getLogger("normal")
request_logger = logging.getLogger("request")

class Request(object):
    """
    代表一个HTTP请求

    Args:
        app: 框架提供的application
        client: 一个连接了客户端（浏览器）的socket连接
        host: 服务器的主机名
        port: 服务器的端口
        addr: 元组，客户端的地址和端口
    """
    def __init__(self, app, client, host, port, addr):
        self.response = client.makefile()
        self.request = client.makefile()
        self.client = client
        self.host = host
        self.port = port
        self.clientaddr = addr
        self.version = "HTTP/1.1"
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
        response_headers.append(("Connection", "Keep-Alive"))
        response_headers.append(("Server", "clwsgi/0.0.1"))
        for header in response_headers:
            response_header += '%s: %s\r\n'%(header[0], header[1]) # 冒号后如果没有空格，ab读取错误
        response_header += "\r\n"
        self.client.send(response_header)
        # request_logger.info("", extra={
        #     "method": "GET",
        #     "ip": self.clientaddr[0],
        #     "path": self.env['PATH_INFO'] + (
        #         "?" + self.env['QUERY_STRING'] if not self.env['QUERY_STRING'] == ""
        #         else "")
        #     })
        return self.response.write

    def serve(self):
        """
        利用该socket连接进行多个请求

        Raises:
            Exception: 捕获所有读取并关闭连接
        """
        timer = gevent.Timeout(5)
        # normal_logger.info("Create new tcp connection")
        with timer:
            try:
                while True:
                    env = self._read_one_requests()
                    # print env
                    for part in self.app(env, self.start_response):
                        self.client.send(part)
                    # self.client.send("\r\n\r\n")
                    if (env["SERVER_PROTOCOL"] == "HTTP/1.0" and ("HTTP_CONNECTION" not in env or env["HTTP_CONNECTION"] != "Keep-Alive")) \
                                                 or \
                                                 "HTTP_CONNECTION" in env and env['HTTP_CONNECTION'] == 'close':
                        self.client.close()
                        break
                    timer.cancel()
                    timer = timer.start_new(5)
            except gevent.timeout.Timeout:
                self.client.close()
            except Exception, ex:
                # traceback.print_exc()
                self.client.close()
            
    
    def _read_one_requests(self):
        """
        从socket中读取一次请求

        Returns:
            env: 本次请求的env字典
        
        Raises:
            Exception: 各类异常，直接抛出到外部关闭连接
        """
        first_line = self.request.readline()
        # 读取到空行
        if not first_line:
            raise Exception("read nothing")
        request_line = first_line.strip().split(' ')
        # 请求行有误
        if len(request_line) != 3 \
            or request_line[2] not in ["HTTP/1.0", "HTTP/1.1"]:
            raise Exception("request line wrong format")
        method, path, version = request_line
        headers = {}
        # 读取所有报文头
        while True:
            line = self.request.readline().strip()
            if line == "":
                break
            x = line.split(":")
            if len(x) >= 2:
                headers['HTTP_'+x[0].strip().upper().replace("-", "_")] = ":".join(x[1:]).strip()
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
            "wsgi.errors": sys.stdout,
            "wsgi.multithread": False,
            "wsgi.multiprocess": False,
            "wsgi.run_once": False
        }
        env.update(headers)
        
        # 将HTTP报文主体读取到StringIO中
        content_length = 0
        if env["CONTENT_LENGTH"]:
            try:
                content_length = int(env["CONTENT_LENGTH"], 10)
            except Exception, ex:
                # content-length非数字
                raise Exception("wrong content-length")
        if content_length > 0:
            buf = StringIO.StringIO(self.client.recv(content_length))
        else:
            buf = StringIO.StringIO("")
        env['wsgi.input'] = buf
        return env

class Worker(multiprocessing.Process):
    def __init__(self, app, host, port, sock):
        multiprocessing.Process.__init__(self)
        self.sock = sock
        self.app = app
        self.host = host
        self.port = port

    def handler(self, client, addr):
        """
        协程，启动一个Request

        Args:
            client: 连接客户端（服务器）的socket连接
            addr: 客户端的地址，二元组，包括地址和端口
        """
        Request(self.app, client, self.host, self.port, addr)
    
    def run(self):
        normal_logger.info("Worker start @pid=%d"%(multiprocessing.current_process().pid))
        while True:
            client, addr = self.sock.accept()
            gevent.spawn(self.handler, client, addr)

class Server(object):
    """
    服务器对象
    
    Args:
        app: 框架提供的application
        host: 服务器端监听的地址
        port: 服务器端监听的端口
    """
    def __init__(self, app, host="0.0.0.0", port=6044, worker=4):
        self.app = app
        self.host = host
        self.port = port
        self.worker = worker
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((host, port))
        self.server.listen(4000)

    def start(self):
        """
        启动服务器
        """
        processes = []
        for i in range(self.worker):
            process = Worker(self.app, self.host, self.port, self.server)
            process.start()
            processes.append(process)

        processes[0].join()

if __name__ == "__main__":
    from flask import Flask

    app = Flask(__name__)
    
    @app.route("/")
    def index():
        return "HELLO"*1000

    server = Server(app, worker=4)
    server.start()