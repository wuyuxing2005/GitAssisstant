# GitIssueAssitant工具接口文档

## 1.概述

本文档说明了 Agent 可用的所有工具接口。这些工具通过 LangChain `@tool` 装饰器暴露给 Agent，支持文件操作、命令执行、代码搜索、Git 操作和测试运行。

## 2.环境依赖

### 2.1python依赖

```markdown
langchain>=0.1.0
langchain-openai>=0.0.5
python-dotenv>=1.0.0
pytest>=7.0.0 # 可选，用于测试运行
```

### 2.2系统依赖（可选但推荐）

- **ripgrep** (rg) :大幅提升代码搜索速度

- **Git**：用于仓库克隆和状态查询

## 3.环境变量

| 变量名                          | 类型 | 默认值       | 说明                                         |
| :------------------------------ | :--- | :----------- | :------------------------------------------- |
| `GIT_ISSUE_ASSISTANT_HOME`      | 路径 | 当前工作目录 | 助手根目录，用于存放克隆的仓库               |
| `GIT_ISSUE_ASSISTANT_REPO_ROOT` | 路径 | 当前工作目录 | 当前操作的仓库根目录，所有路径解析以此为基准 |

**注意**：`SessionManager` 会在切换仓库时自动设置 `GIT_ISSUE_ASSISTANT_REPO_ROOT`，工具会读取此变量来确定工作目录。

## 4.通用行为

### 4.1 路径安全

所有文件操作都被限制在 `GIT_ISSUE_ASSISTANT_REPO_ROOT` 目录内，尝试访问外部路径会抛出错误。

### 4.2 输出截断

单个工具输出超过 `12000` 字符会被截断，末尾添加 `...<truncated>` 标记。

### 4.3 错误处理

工具执行失败时返回以 `"Error:"` 开头的错误信息，Agent 可通过检测前缀判断成功/失败。

## 5. 工具列表

### 5.1 文件操作类

#### 5.1.1 `read_file`

**功能**：读取文件内容，返回带行号的文本。

**签名**：

```python
read_file(file_path: str, start_line: int = 1, end_line: int = 200) -> str
```

**参数**：

| 参数         | 类型 | 默认值 | 说明                         |
| :----------- | :--- | :----- | :--------------------------- |
| `file_path`  | str  | 必填   | 文件路径（相对于仓库根目录） |
| `start_line` | int  | 1      | 起始行号（从1开始）          |
| `end_line`   | int  | 200    | 结束行号（包含）             |

**返回值**：

```
1|import os
2|
3|def main():
4|    print("hello")
...
```

**错误返回**：

```
No content found in src/main.py for lines 1-200.
```

#### 5.1.2 `write_file`

**功能**：创建新文件或覆盖已有文件。

**签名**：

```python
write_file(file_path: str, content: str) -> str
```

**参数**：

| 参数        | 类型 | 默认值 | 说明                         |
| :---------- | :--- | :----- | :--------------------------- |
| `file_path` | str  | 必填   | 文件路径（相对于仓库根目录） |
| `content`   | str  | 必填   | 要写入的内容                 |

**返回值**：

```
Wrote 1234 characters to src/main.py
```

#### 5.1.3 `replace_in_file`

**功能**：精确文本替换，支持单次或全部替换。

**签名**：

```python
replace_in_file(file_path: str, old_text: str, new_text: str, replace_all: bool = False) -> str
```

**参数**：

| 参数          | 类型 | 默认值 | 说明                         |
| :------------ | :--- | :----- | :--------------------------- |
| `file_path`   | str  | 必填   | 文件路径                     |
| `old_text`    | str  | 必填   | 要替换的文本（必须精确匹配） |
| `new_text`    | str  | 必填   | 替换后的文本                 |
| `replace_all` | bool | False  | 是否替换所有匹配项           |

**返回值**：

```
Updated src/main.py; replaced 1 occurrence(s).
```

**错误返回**：

```
Error: old_text was not found in the file.
Error: old_text matched 3 times. Set replace_all=True or use a more specific snippet.
```

#### 5.1.4 `patch_file`

**功能**：使用 SEARCH/REPLACE 格式打补丁，支持多个补丁块。

**签名**：

```
patch_file(file_path: str, diff_content: str) -> str
```

**参数**：

| 参数           | 类型 | 默认值 | 说明                             |
| :------------- | :--- | :----- | :------------------------------- |
| `file_path`    | str  | 必填   | 文件路径                         |
| `diff_content` | str  | 必填   | 包含 SEARCH/REPLACE 块的补丁内容 |

**补丁格式**：

```
<<<<<<< SEARCH
def old_function():
    return "old"
=======
def new_function():
    return "new"
>>>>>>> REPLACE
```

支持多个补丁块连续使用。

**返回值**：

```
Applied 2 patch block(s) to src/main.py
```

**错误返回**：

```
Error: no valid patch blocks found. Use the format: ...
Error: patch block 1 SEARCH text was not found.
Error: patch block 2 SEARCH text matched 3 times.
```

### 5.2 代码搜索类

#### 5.2.1 `search_code`

**功能**：使用正则表达式搜索代码。优先使用 ripgrep（速度快），降级到 Python 正则。

**签名**：

```python
search_code(pattern: str, search_path: str = ".", file_glob: str = "*", case_sensitive: bool = False, max_results: int = 100) -> str
```

**参数**：

| 参数             | 类型 | 默认值 | 说明                      |
| :--------------- | :--- | :----- | :------------------------ |
| `pattern`        | str  | 必填   | 正则表达式模式            |
| `search_path`    | str  | "."    | 搜索起始路径              |
| `file_glob`      | str  | "*"    | 文件匹配模式（如 "*.py"） |
| `case_sensitive` | bool | False  | 是否大小写敏感            |
| `max_results`    | int  | 100    | 最大返回结果数            |

**返回值**：

```
src/main.py:10: def calculate():
src/main.py:25: result = calculate()
src/utils.py:5: def calculate_sum():
```

#### 5.2.2 `list_files`

**功能**：列出目录中的文件。

**签名**：

```python
list_files(path: str = ".", recursive: bool = True, file_glob: str = "*", limit: int = 200) -> str
```

**参数**：

| 参数        | 类型 | 默认值 | 说明               |
| :---------- | :--- | :----- | :----------------- |
| `path`      | str  | "."    | 目录路径           |
| `recursive` | bool | True   | 是否递归列出子目录 |
| `file_glob` | str  | "*"    | 文件匹配模式       |
| `limit`     | int  | 200    | 最大返回文件数     |

**返回值**：

```
src/main.py
src/utils.py
tests/test_main.py
```

### 5.3 命令执行类

#### 5.3.1 `bash_terminal`

**功能**：在仓库根目录执行 Shell 命令。

**签名**：

```python
bash_terminal(command: str, timeout_seconds: int = 60) -> str
```

**参数**：

| 参数              | 类型 | 默认值 | 说明                |
| :---------------- | :--- | :----- | :------------------ |
| `command`         | str  | 必填   | 要执行的 Shell 命令 |
| `timeout_seconds` | int  | 60     | 超时时间（秒）      |

**返回值**：

```
Command output line 1
Command output line 2
[STDERR]
Error output if any
```

#### 5.3.2 `run_pytest`

**功能**：运行 pytest 测试。

**签名**：

```python
run_pytest(pytest_args: str = "", working_dir: str = ".") -> str
```

**参数**：

| 参数          | 类型 | 默认值 | 说明                                      |
| :------------ | :--- | :----- | :---------------------------------------- |
| `pytest_args` | str  | ""     | pytest 命令行参数（如 "-k test_name -v"） |
| `working_dir` | str  | "."    | 测试运行的工作目录                        |

**返回值**：

```
============================= test session starts ==============================
collected 5 items

tests/test_main.py ....F                                               [100%]

=================================== FAILURES ===================================
...
```

### 5.4 Git 操作类

#### 5.4.1 `git_clone_repo`

**功能**：克隆 Git 仓库到本地。

**签名**：

```python
git_clone_repo(repo_url: str, target_dir: str, branch: str = "", depth: int = 0) -> str
```

**参数**：

| 参数         | 类型 | 默认值 | 说明                         |
| :----------- | :--- | :----- | :--------------------------- |
| `repo_url`   | str  | 必填   | Git 仓库 URL                 |
| `target_dir` | str  | 必填   | 目标目录名                   |
| `branch`     | str  | ""     | 指定分支（可选）             |
| `depth`      | int  | 0      | 浅克隆深度（0 表示完整克隆） |

#### 5.4.2 `git_status`

**功能**：显示 Git 工作区状态。

**签名**：

```python
git_status(repo_path: str = ".") -> str
```

#### 5.4.3 `git_diff`

**功能**：显示代码变更差异。

**签名**：

```python
git_diff(repo_path: str = ".", staged: bool = False) -> str
```

**参数**：

| 参数        | 类型 | 默认值 | 说明               |
| :---------- | :--- | :----- | :----------------- |
| `repo_path` | str  | "."    | 仓库路径           |
| `staged`    | bool | False  | 是否显示暂存区差异 |

### 5.5 辅助工具

#### 5.5.1 `current_repo_info`

**功能**：获取当前仓库和助手根目录信息。

**签名**：

```python
current_repo_info() -> str
```

**返回值**：

```
assistant_root=/home/user/assistant
repo_root=/home/user/assistant/repos/myproject
repo_root_relative=repos/myproject
```