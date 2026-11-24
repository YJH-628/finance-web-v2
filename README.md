# FinanceAI V2

独立交付的 Vue 3 财务工作台。`frontend` 使用 Vite、Chart.js 和 Lucide 图标，`backend` 包含完整 Flask、SQLite、DeepSeek API 实现，不依赖原版目录或外部代码动态加载。

## 目录结构

```text
finance-web-v2/
├── backend/
│   ├── app.py
│   ├── config.example.ini
│   ├── config.ini
│   ├── finance.db
│   └── requirements.txt
├── frontend/
│   ├── src/
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
└── README.md
```

## 启动

后端终端：进入 `backend` 目录，运行 `pip install -r requirements.txt`，然后运行 `python app.py`。需要 AI 时，将 `config.example.ini` 复制为 `config.ini`，填写自己的 DeepSeek API Key。未配置 AI 时仍可使用账本功能。

前端构建终端：进入 `frontend` 目录，运行 `npm ci`、`npm run build`。

生产访问地址为 **http://127.0.0.1:5532**。后端可用环境变量 `PORT` 更改端口。

开发前端时，保持后端运行，在 `frontend` 目录执行 `npm run dev`，访问 http://127.0.0.1:5533；Vite 将 `/api` 转发到 5532。

## 数据与配置

- 完整交付本项目即可，无需原版 `finance-web` 目录。原版保持不变。
- 数据库固定为 `backend/finance.db`，已有 V2 数据已保留；数据库不存在时初始化空账本与默认分类，不再读取或复制原版数据。
- 交付第三方时使用 `config.example.ini`，不要携带个人 `config.ini` 密钥或真实账本；`node_modules`、`__pycache__` 不必交付。
- 新增、删除、导入、清空只影响 V2。CSV 导入是追加操作，不自动去重。演示数据、随机数据同样是追加。
- CSV 列名为 `日期,分类,类型,金额,描述`，推荐 UTF-8 编码；导出为带 BOM 的 CSV。
- CSV 必须包含日期、分类、类型、金额，描述可选；任一行无效将拒绝整个文件，不产生部分导入。上传上限 5 MB，金额须为正数且最多两位小数。
- 总览与明细支持月份筛选；AI 使用全部账本摘要，并通过本项目 `backend/config.ini` 配置的 DeepSeek 服务处理，需网络和有效 API 配置。
- V2 修复了只有支出、没有收入时生成 AI 摘要的除零问题，原版文件保持不变。

## 功能

财务总览、收入支出趋势、支出分类图、记录新增删除、搜索筛选与分页、分类管理、CSV 导入导出、演示数据、AI 财务分析及流式问答。支持桌面和移动端。

## 交付检查

- 本系统是本机单用户工具，无登录和权限隔离，默认仅监听 `127.0.0.1`。不要直接开放到公网；公网或多人使用需要额外认证和正式部署方案。
- 交付保留 `backend/app.py`、`backend/test_app.py`、`backend/requirements.txt`、`backend/config.example.ini`、前端源码/依赖清单/配置、README。可附 `frontend/dist` 方便直接启动。
- 排除 `backend/config.ini`、`backend/finance.db`、`__pycache__`、`frontend/node_modules`，避免泄露密钥及个人数据。
- Python 3.10+、Node.js 20.19+（推荐当前 LTS）。前端安装依赖需要网络，AI 调用需要网络；日常本地记账不需要联网。
- 后端回归：在 `backend` 执行 `python -m unittest -v`，测试使用临时账本，AI 使用模拟响应，不收费、不联网。