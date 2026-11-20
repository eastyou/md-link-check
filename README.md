# md-link-check

[![CI](https://github.com/eastyou/md-link-check/actions/workflows/ci.yml/badge.svg)](https://github.com/eastyou/md-link-check/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-brightgreen.svg)](pyproject.toml)

一个零依赖的 Markdown 链接检查工具：本地相对路径、标题锚点、外部 HTTP 链接，一次全部检查完，可直接放进 CI。

仓库里的文档一多，改名、移动文件之后很容易留下死链。`mdlink` 会扫描所有 `.md` 文件，跳过代码块里的示例链接，把真正的问题按文件和行号列出来。

## 特性

- **本地路径检查**：`[文档](docs/guide.md)`、图片、`%20` 转义都能识别
- **标题锚点检查**：`[跳转](guide.md#快速开始)` 会校验目标文件里是否真的存在该标题
- **外部链接检查**：多线程并发、HEAD 失败自动回退 GET、可配置超时
- **跳过代码内容**：代码块和行内代码中的链接不会被误报
- **CI 友好**：发现问题时退出码为 1，可直接用于 GitHub Actions
- **零依赖**：只使用 Python 标准库，Python 3.9+

## 安装

```bash
pip install "git+https://github.com/eastyou/md-link-check.git"
```

或本地使用：

```bash
git clone https://github.com/eastyou/md-link-check.git
cd md-link-check
python3 -m pip install -e .
```

不安装也能运行：`python3 -m mdlinkcheck README.md --offline`

## 使用

```console
$ mdlink docs
docs/guide.md:12  [local]  getting-started.md  本地路径不存在: getting-started.md
docs/guide.md:30  [external]  https://example.com/old  HTTP 404

检查 8 个文件，发现 2 个链接问题
```

```bash
# 只检查本地链接和锚点，不访问网络
mdlink docs --offline

# 输出 JSON，方便脚本处理
mdlink . --json

# 排除指定目录，可重复传入
mdlink . --exclude node_modules --exclude .venv

# 调整超时与并发
mdlink docs --timeout 5 --concurrency 16
```

### 参数

| 参数 | 说明 |
| --- | --- |
| `PATH ...` | Markdown 文件或目录，默认当前目录 |
| `--offline` | 跳过外部链接 |
| `--exclude GLOB` | 排除匹配的目录或文件，可重复 |
| `--timeout SEC` | 单个外部链接的超时时间，默认 10 秒 |
| `--concurrency N` | 外部链接并发数，默认 8 |
| `--json` | JSON 输出 |
| `--quiet` | 只输出问题 |

### 退出码

| 退出码 | 含义 |
| --- | --- |
| `0` | 没有发现问题 |
| `1` | 存在失效链接 |
| `2` | 参数或路径错误 |

## 在 CI 中使用

```yaml
- name: Check Markdown links
  run: |
    pip install "git+https://github.com/eastyou/md-link-check.git"
    mdlink . --exclude node_modules
```

## 实现说明

- 扫描前会把代码块、行内代码替换成等长空白，保证行号不变且不会误报
- 外部链接先去重再并发检查，避免同一 URL 重复请求
- 锚点采用近似 GitHub 的 slug 规则：小写、去标点、空格转 `-`
- 暂不支持跨行复杂链接与 HTML `<a>` 标签，聚焦最常见的 Markdown 语法

## 开发与测试

```bash
python3 -m unittest discover -s tests -v
```

## License

[MIT](LICENSE) © 2026 eastyou
