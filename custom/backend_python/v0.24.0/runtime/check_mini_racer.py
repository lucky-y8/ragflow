"""检查 JavaScript 引擎的提供方和真实调用，构建与镜像自检共用。"""

import importlib.metadata


def check_mini_racer():
    # 这些发行包使用同一导入目录；先检查冲突，再导入，避免安装顺序决定实际实现。
    for package in ("akracer", "py-mini-racer"):
        try:
            version = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            continue
        raise RuntimeError(f"发现冲突包 {package}=={version}：它会覆盖 mini-racer 的 py_mini_racer 模块。请使用本目录更新后的依赖锁文件重新构建镜像。")
    version = importlib.metadata.version("mini-racer")
    assert version == "0.12.4", f"mini-racer 版本与锁文件不符：{version}"

    from py_mini_racer import MiniRacer

    # 同时覆盖 AkShare 所用的 eval / call / execute 接口。
    with MiniRacer() as runtime:
        assert runtime.eval("1 + 1") == 2
        runtime.eval("function add(a, b) { return a + b; }")
        assert runtime.call("add", 2, 3) == 5
        assert runtime.execute('({"ok": true, "items": [1, 2]})') == {"ok": True, "items": [1, 2]}
    print(f"JavaScript 引擎自检通过：mini-racer {version}")


if __name__ == "__main__":
    check_mini_racer()
