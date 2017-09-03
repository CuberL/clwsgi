# clwsgi

clwsgi是一个基于gevent的WSGI服务器，实现标准是PEP333，可以与实现WSGI的框架搭配使用。

## 使用示例

```python
from flask import Flask
from clwsgi import Server

app = Flask(__name__)

@app.route("/")
def index():
    return "Hello, World"

server = Server(app)
app.start()
```

## 其他设置

### 指定worker数量

```python
server = Server(app, worker=8)
server.start()
```

### 指定地址、端口

```python
server = Server(app, host="0.0.0.0", port=8080)
server.start()
```

