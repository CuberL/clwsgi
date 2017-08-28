from setuptools import setup, find_packages

setup(
    name="clwsgi",
    version='0.0.1',
    description="a wsgi server base on gevent",
    keywords="wsgi server",
    author="cuberl",
    author_email="liaoziyue10@gmail.com",
    url="http://github.com/cuberl",
    packages=find_packages(),
    package_data={
        'clwsgi':['logger.conf']
    },
    include_package_data=True,
    zip_safe=False,
    install_requires=[
        "gevent"
    ]
)
