"""镜像离线自检；实际数据库连接和文档解析须在平台联调时验证。"""

import platform
import sys
from pathlib import Path

import cv2
import nltk
import numpy
import onnxruntime
import peewee
import quart
import xgboost
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from check_mini_racer import check_mini_racer

assert platform.machine() == "aarch64"
assert sys.version_info[:2] == (3, 12)
assert Path("/ragflow/VERSION").read_text().strip() == "v0.24.0"
assert "CPUExecutionProvider" in onnxruntime.get_available_providers()
assert cv2.cvtColor(numpy.zeros((2, 2, 3), dtype=numpy.uint8), cv2.COLOR_BGR2GRAY).shape == (2, 2)
assert xgboost.__version__ == "1.6.0"
assert peewee.__version__ and quart.Quart
check_mini_racer()
assert nltk.word_tokenize("ARM test.") == ["ARM", "test", "."]
from nltk.corpus import wordnet

assert wordnet.synsets("test")
options = Options()
options.binary_location = "/opt/chrome/chrome"
for flag in ("--headless", "--no-sandbox", "--disable-dev-shm-usage"):
    options.add_argument(flag)
with webdriver.Chrome(service=Service("/usr/local/bin/chromedriver"), options=options) as browser:
    browser.get("data:text/html,<title>arm64-v0240-ok</title>")
    assert browser.title == "arm64-v0240-ok"
print("v0.24.0 ARM64 自检通过：Python 3.12、原生依赖、NLTK 和浏览器运行正常。")
