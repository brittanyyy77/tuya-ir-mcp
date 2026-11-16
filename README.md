# tuya-ir-mcp

用涂鸦红外遥控器 + MCP 协议，让 AI 远程控制任何红外设备——哄睡玩偶、空调、灯、风扇，只要能学码就能控。

## 架构

```
AI 客户端 (Aru / Claude / GPT)
    ↓ MCP (streamable-http)
https://你的域名/mcp
    ↓ Cloudflare Tunnel
localhost:18088 (Flask MCP 服务)
    ↓ 涂鸦云 API
https://openapi.tuyacn.com
    ↓ 红外信号
涂鸦红外遥控器 → 你的设备
```

## 目录

- [准备工作](#准备工作)
- [第一步：涂鸦平台配置](#第一步涂鸦平台配置)
- [第二步：红外学码](#第二步红外学码)
- [第三步：部署 MCP 服务](#第三步部署-mcp-服务)
- [第四步：Cloudflare Tunnel 穿透](#第四步cloudflare-tunnel-穿透)
- [第五步：接入 AI 客户端](#第五步接入-ai-客户端)
- [工具列表](#工具列表)
- [踩坑记录](#踩坑记录)
- [自定义按键映射](#自定义按键映射)

---

## 准备工作

| 你需要 | 说明 |
|---------|------|
| 涂鸦红外遥控器 | 淘宝搜“涂鸦红外遥控器”，20-50 元，必须支持**红外学习**（DIY 学码） |
| 带红外遥控器的设备 | 哄睡玩偶、空调、灯、风扇等，只要有红外遥控器就行 |
| 智能生活 App | 手机应用商店下载「智能生活」 |
| 一台电脑 | Mac / Linux / Windows，跑 MCP 服务用 |
| Python 3.9+ | `python3 --version` 检查 |

## 第一步：涂鸦平台配置

### 1. 手机端

1. 下载「智能生活」App，注册账号
2. 添加设备 → 万能遥控 → 红外遥控器 → 连接 WiFi
3. 确认设备在线

### 2. 开发者平台

1. 打开 [platform.tuya.com](https://platform.tuya.com)
2. 用智能生活 App 的账号登录
3. 进入「云开发」→「项目管理」→ 创建新项目
4. 记下 **Access ID** 和 **Access Secret**
5. 在「云服务」确认「IoT Core 连接服务」已开通
6. 在「设备」里关联你的智能生活 App 账号下的设备
7. 记下红外遥控器的 **设备 ID**（在设备列表里）

## 第二步：红外学码

1. 在智能生活 App 里进入红外遥控器
2. 添加遥控器 → 拉到底部选 **DIY 自定义学习**
3. 填写信息：类目「其他」，品牌「其他」，型号随便填
4. 拿原装遥控器**对准**涂鸦红外遥控器的接收口
5. App 点“学习” → 按原装遥控器对应按钮 → 学一个命名一个
6. 全部学完后在 App 里逐个点测试

> **重要**：红外遥控器必须能直接照到设备的红外接收口，不能隔墙、不能被挡住。

## 第三步：部署 MCP 服务

### 1. 克隆仓库

```bash
git clone https://github.com/brittanyyy77/tuya-ir-mcp.git
cd tuya-ir-mcp
```

### 2. 安装依赖

```bash
pip3 install flask requests
```

### 3. 配置凭据

```bash
cp .env.example .env
chmod 600 .env
nano .env
```

填入你的涂鸦凭据：

```
TUYA_ACCESS_ID=你的Access_ID
TUYA_ACCESS_SECRET=你的Access_Secret
TUYA_IR_DEVICE_ID=你的红外遥控器设备ID
TUYA_ENDPOINT=https://openapi.tuyacn.com
PORT=18088
```

> **端点选择**：国内用 `openapi.tuyacn.com`，海外用 `openapi.tuyaus.com` 或 `openapi.tuyaeu.com`。VPS 在国外但用国内端点会报跨区错误，建议从本地电脑跑。

### 4. 启动

```bash
python3 server.py
```

看到 `Connected! Remote: xxx` 和按键列表就说明连通了。

### 5. 本机测试

```bash
curl -sS http://127.0.0.1:18088/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

返回 6 个工具就对了。

## 第四步：Cloudflare Tunnel 穿透

让外网的 AI 客户端能访问你本地跑的 MCP 服务。

### 1. 安装 cloudflared

```bash
# Mac
brew install cloudflare/cloudflare/cloudflared

# Ubuntu/Debian
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb
```

### 2. 登录并创建 Tunnel

```bash
cloudflared tunnel login
cloudflared tunnel create pillow
```

### 3. 配置路由

编辑 `~/.cloudflared/config.yml`：

```yaml
tunnel: 你的Tunnel_ID
credentials-file: ~/.cloudflared/你的Tunnel_ID.json

ingress:
  - hostname: pillow.你的域名.com
    service: http://localhost:18088
  - service: http_status:404
```

### 4. 添加 DNS 并启动

```bash
cloudflared tunnel route dns pillow pillow.你的域名.com
cloudflared tunnel run pillow
```

### 5. 验证

```bash
curl -sS https://pillow.你的域名.com/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## 第五步：接入 AI 客户端

| 配置项 | 填写内容 |
|--------|----------|
| 名称 | 拍拍抱枕（或你的设备名） |
| URL | `https://pillow.你的域名.com/mcp` |
| 传输类型 | streamable-http |

## 工具列表

| 工具名 | 说明 |
|--------|------|
| `pillow_status` | 检查连接状态和可用按键 |
| `pillow_power` | 开/关机（toggle） |
| `pillow_pat_toggle` | 拍打开/关（toggle） |
| `pillow_speed_up` | 拍打加快 |
| `pillow_speed_down` | 拍打减慢 |
| `pillow_light` | 灯光开/关（toggle） |

> **注意**：开关机和拍打都是 toggle，按多了会搅乱状态。操作前建议先确认设备当前状态。

## 踩坑记录

| # | 现象 | 原因 | 解法 |
|---|------|------|------|
| 1 | VPS 调涂鸦 API 报跨区错误 | VPS 在国外，涂鸦云在国内 | 服务跑在国内机器或本地电脑上，用 Cloudflare Tunnel 穿出去 |
| 2 | 红外指令发了但设备没反应 | 遥控器没对准设备红外接收口，或距离太远 | 调整遥控器位置，确保红外直线可达 |
| 3 | 开关机按多了状态搅乱 | 开关机是 toggle，不是独立的 on/off | 操作前确认设备状态，不要连续发 |
| 4 | 涂鸦 token 过期 | 涂鸦云 token 有有效期 | 代码已内置自动续期，不用手动处理 |
| 5 | 涂鸦 IoT Cloud 免费版调用次数限制 | 免费版有配额 | 正常使用完全够，过期可用 tinytuya 走局域网本地控制 |

## 自定义按键映射

如果你控制的不是哄睡玩偶，而是空调、灯或其他设备，你需要修改 `server.py` 里的两个地方：

1. **TOOLS 列表**：改成你的设备对应的工具名和描述
2. **KEY_MAP 字典**：把工具名映射到你在涂鸦 App 里学码时命名的按键名

按键名可以通过 `pillow_status` 工具查看，或在涂鸦开发者平台的设备页查看。

## 致谢

- [顾川 & 派派](https://github.com/BB0813) — 原始红外接入攻略
- [涂鸦开发者平台](https://platform.tuya.com) — IoT 云 API

## License

MIT
