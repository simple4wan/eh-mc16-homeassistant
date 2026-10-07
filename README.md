# HONYAR ICH8403TM / EH-MC16 Home Assistant BLE Firmware

将 **鸿雁智能插座 HONYAR ICH8403TM** 从原厂 **天猫精灵 Bluetooth Mesh** 固件改造成可直接接入 Home Assistant 的本地 BLE 智能插座。

本项目使用插座内部的 **Ehong EH-MC16 V3.1 / Realtek Bee2 (RTL8762C 系列)** 蓝牙模块，保留本地按键、继电器、双色 LED 和 Realtek BLE OTA 能力，不需要 Wi-Fi 配网，也不依赖天猫精灵云端。

> 当前项目已经完成原厂设备的直接 BLE OTA 验证。原厂 `EH-MC16-CZ` 可以直接通过 silent OTA 刷入本项目固件，不需要先刷过渡固件，也不需要拆机连接 TTL。

---

## 支持设备

已确认的目标设备：

- 品牌：**鸿雁 / HONYAR**
- 产品：**鸿雁智能插座**
- 型号：**ICH8403TM**
- 原厂生态：**天猫精灵 Bluetooth Mesh**
- BLE 模块：**Ehong EH-MC16 V3.1**
- SoC：**Realtek Bee2 / RTL8762C 系列**
- 原厂 BLE 名称：`EH-MC16-CZ`
- 本项目 BLE 名称：`EH-MC16-HA`

本项目目前只针对已实测的上述硬件。即使其他设备也使用 EH-MC16，也请先确认 GPIO 和 Flash 布局一致后再刷。

---

## 当前功能

固件目前提供：

- 本地物理按键控制
- BLE 控制继电器
- BLE 读取当前开关状态
- Home Assistant 自定义集成自动发现
- 支持多只插座
- 支持 Home Assistant 本机蓝牙
- 支持 ESPHome Bluetooth Proxy
- 保留 Realtek BLE OTA
- 上电默认关闭插座
- 关闭时红灯
- 开启时蓝灯

当前不包含：

- Wi-Fi
- 云端服务
- 天猫精灵配网
- BLE bonding / pairing
- 功率、电流、电压计量

该型号当前确认没有可用的功率计量硬件路径，本项目将它作为普通 BLE 开关使用。

---

## 已确认硬件 GPIO

| 功能 | GPIO | 行为 |
| --- | --- | --- |
| 按键 | `P3_2` | 低电平有效 |
| 继电器 | `P2_5` | HIGH = ON，LOW = OFF |
| 红灯 | `P2_2=HIGH, P2_3=LOW` | 插座关闭 |
| 蓝灯 | `P2_2=LOW, P2_3=HIGH` | 插座开启 |

---

## BLE 控制协议

为了保持固件简单并继续复用 Realtek 原有 OTA 服务，本项目复用了 D0FF 服务中的两个特征。

### 服务

```text
0000d0ff-3c17-d293-8e48-14fe2e4da212
```

### 状态读取

Characteristic：

```text
0000ffd5-0000-1000-8000-00805f9b34fb
```

读取 1 byte：

```text
00 = OFF
01 = ON
```

### 开关控制

Characteristic：

```text
0000ffd8-0000-1000-8000-00805f9b34fb
```

写入 1 byte：

```text
00 = OFF
01 = ON
02 = TOGGLE
```

---

## Home Assistant 集成

仓库内已经包含：

```text
custom_components/eh_mc16/
├── __init__.py
├── config_flow.py
├── const.py
├── manifest.json
├── strings.json
└── switch.py
```

复制到 Home Assistant：

```text
/config/custom_components/eh_mc16/
```

然后重启 Home Assistant。

只要 Home Assistant 能通过本机蓝牙或 ESPHome Bluetooth Proxy 收到 `EH-MC16-HA`，设备会通过 Bluetooth discovery 被发现。

在：

```text
设置
→ 设备与服务
→ 已发现
```

添加即可。

每只插座使用独立 BLE 地址作为唯一 ID，因此支持多设备同时加入 Home Assistant。

---

## 原厂设备直接 OTA

### 环境

macOS / Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 固件文件

使用 GitHub Actions 生成的：

```text
EH-MC16-HA-BLE_MP.bin
```

当前 HA BLE 固件基于原始 SDK 的 stock flash layout：

```text
AppPatch : 0x0080E000
App size : 0x17000
FTL      : 0x00825000
FTL size : 0x4000
OTA TMP  : 0x00829000
OTA size : 0x17000
```

### 直接刷原厂插座

一次只给一只待刷插座上电，避免多只同名设备同时出现。

原厂 BLE 名称：

```text
EH-MC16-CZ
```

执行：

```bash
python tools/ble_dfu.py \
  --name EH-MC16-CZ \
  --image EH-MC16-HA-BLE_MP.bin \
  --flash \
  --yes
```

工具会：

1. 扫描并连接原厂 `EH-MC16-CZ`
2. 验证 Bee2 `ic_type = 0x05`
3. 查询 AppPatch 信息
4. 读取原厂 OTA policy
5. 使用 Realtek reference AES-256 key 进行加密 OTA
6. 使用 buffer-check 分块传输
7. 校验完整镜像
8. 等待人工确认激活

成功传输后会看到：

```text
validation successful

Firmware has been transferred and validated, but is NOT active yet.
Type ACTIVATE to switch to the new image and reboot
```

输入：

```text
ACTIVATE
```

设备断开 BLE 并重启属于正常现象。

重启后应广播：

```text
EH-MC16-HA
```

随后测试：

- 按键能切换继电器
- OFF 为红灯
- ON 为蓝灯
- Home Assistant 能发现设备

---

## 已验证的原厂 OTA 参数

原厂设备通过 D0FF / FFF1 返回：

```text
05 01 00 07 00 08 00 00 30 0f 00 00
```

解析结果：

- IC type：`0x05`
- OTA version：`1`
- buffer check：支持
- AES：开启
- AES all：开启
- max buffer：`2048`

AppPatch：

```text
image_id = 0x2793
```

当前固件实测可以从原厂应用模式直接走 silent OTA，不需要先切换到独立 BeeTgt OTA 模式。

---

## Realtek DFU 服务

原厂和本项目均基于 Realtek Bee2 DFU：

```text
Service : 00006287-3c17-d293-8e48-14fe2e4da212
Data    : 00006387-3c17-d293-8e48-14fe2e4da212
Control : 00006487-3c17-d293-8e48-14fe2e4da212
```

已确认：

```text
RECEIVE_IC_TYPE (0x0B)
→ 10 0B 01 05
```

即：

```text
ic_type = 0x05
```

---

## TTL / ROM 恢复

正常刷原厂设备 **不需要 TTL**。

TTL / ROM boot 仅用于：

- 设备无法正常启动
- BLE OTA 已不可用
- 需要做完整 Flash 恢复
- 开发调试

EH-MC16 已确认引脚：

| EH-MC16 引脚 | 功能 |
| --- | --- |
| 1 / 13 / 16 | GND |
| 2 | UART TX |
| 3 | UART RX |
| 4 | SWDIO / P1_0 |
| 5 | SWDCLK / P1_1 |
| 7 | P0_3 / LOG / ROM boot |
| 14 | RESET |
| 15 | 3.3V |

ROM boot 时需要在上电期间将 `P0_3` 拉低。

### 安全警告

**绝对不要在插座接入市电时连接 PC USB-TTL、SWD 或 J-Link。**

智能插座内部低压侧可能与市电不隔离。TTL / SWD 调试时必须：

- 拔掉市电
- 使用独立、安全的 3.3V 供电
- 确认 UART 电平为 3.3V
- 共地
- 调试完成后拆掉所有 TTL / SWD 线，再接市电测试

不要使用 CH340 的 3.3V 输出直接给整块插座主板供电，除非已经确认电流能力和电路安全。

---

## 编译

GitHub Actions 会自动：

1. 拉取 RTL8762C GCC SDK
2. 应用 `scripts/patch_ha_ble.py`
3. 验证 stock flash layout
4. 编译 HA BLE 固件
5. 上传固件 artifact

当前 SDK：

```text
https://github.com/wuwbobo/rtl8762c-sdk-gcc
commit: 88aa8c7b72370f86a0841a07610901ef4091094e
```

当前 CI 只构建 HA BLE 固件，不再自动构建之前实验阶段的 HomeKit / bridge 固件。

---

## 项目状态

目前已经完成：

- [x] EH-MC16 / Bee2 芯片确认
- [x] 原厂 BLE GATT / DFU 分析
- [x] 原厂 Flash layout 确认
- [x] GPIO 按键识别
- [x] 继电器 GPIO 识别
- [x] 双色 LED GPIO 识别
- [x] 本地按键控制
- [x] BLE 状态读取
- [x] BLE 开 / 关控制
- [x] 保留 Realtek OTA
- [x] 原厂 HONYAR ICH8403TM 直接 silent OTA 验证
- [x] Home Assistant custom component
- [x] 多设备唯一 ID
- [x] Home Assistant Bluetooth / ESPHome Bluetooth Proxy 路径

后续可以继续完善：

- [ ] BLE 状态 Notify，减少 HA 轮询
- [ ] Home Assistant 集成长期稳定性测试
- [ ] OTA 升级 `EH-MC16-HA → EH-MC16-HA` 的完整回归测试
- [ ] 更完善的错误恢复和版本显示
- [ ] HACS 打包（如有需要）

---

## 免责声明

刷写第三方固件存在设备失效风险。

本项目涉及市电智能插座。任何拆机、TTL、SWD 或裸板调试都必须在完全断开市电的情况下进行。

使用本项目即表示你理解并自行承担刷写和硬件改造风险。
