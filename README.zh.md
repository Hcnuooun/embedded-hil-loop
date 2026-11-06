# embedded-hil-loop（嵌入式硬件在环开发 skill）

给 AI Agent（以及盯着它的人）用的一个 skill：把一块真实的 MCU 板子变成**快、可重复**的开发回路 ——
不需要人帮忙点屏幕、描述现象、或者手动烧程序。

它把三件事和让这三件事可信的纪律打包在一起：

| | |
|---|---|
| **探针** | 直接读写运行中的变量、看计数器、烧写并核对 —— 不用 `printf`，不用为了看一眼就重烧 |
| **注入** | 通过调试器改触摸输入缓存，UI 测试变成脚本 |
| **抓屏** | 把显示层的显存抓成 PNG，"看着对"变成证据 |
| 另外 | 单缓冲显示的扫描预算算法，以及一批最贵的坑的目录 |

样本工程是 STM32H743 + 800×480 LTDC 屏 + LVGL：单前缓冲、没有 DMA2D、没有双缓冲。
参考资料里的每个数字都是在那块板上量出来的。方法本身与芯片无关；抓屏/解码那一段是 STM32 LTDC 专用。

## 为什么要有它

看不见板子的 Agent 只能读代码猜。常见的替代办法是"你烧一下、点一下、告诉我看到什么"——
每验证一个猜想就要人来回一次，而且得到的证据没法 diff、没法回放、没法存档。

这个 skill 就是被这种慢逼出来的。一个真实例子：切页后绘图区正确，但右侧面板还是上一页的。
读变量 `s_page` 说已经切了，截图说没有；再加一个计数器才发现重绘调度被一个两行的预算误差锁死了。
能在几分钟内定位，靠的就是"屏幕可以脚本化地点、脚本化地抓"。

## 目录

```
embedded-hil-loop/
├── SKILL.md                       # Agent 加载的正文（流程、规则、症状对照表）
├── README.md / README.zh.md       # 本文件
├── PUBLISH.md                     # 发布前检查清单
├── CHANGELOG.md
├── references/
│   ├── protocol.md                # 与人的协作约定：先读现状、证据、逐项授权、交接
│   ├── probe-recipes.md           # J-Link 配方、结构体偏移、命令字、时间测量的有效性
│   ├── ui-harness.md              # 合成触摸、抓屏、PC 预览、断言
│   ├── scanout-budget.md          # 撕裂预算、分带擦入、实测数字、死锁案例
│   └── pitfalls.md                # 15 个坑：现象 → 原因 → 修法 → 下次怎么抓
├── scripts/
│   ├── jprobe.py                  # J-Link 读/看/写/烧/抓屏
│   ├── synth_touch.py             # 通过输入缓存 tap/press/move/release
│   └── validate_skill.py          # skill 包发布前自检
└── assets/
    ├── AGENTS.template.md         # 工程说明文件骨架
    └── handover.template.md       # 交接骨架（现状 / 过时 / 下一步）
```

## 安装

文件系统 skill 就是一个目录：根下放 `SKILL.md`，放在任意被扫描的 skill 根目录里即可。

```bash
# 用户级（所有工程可用）
cp -r embedded-hil-loop ~/.dsh/skills/

# 或者工程级（跟仓库一起提交）
mkdir -p .dsh/skills && cp -r embedded-hil-loop .dsh/skills/
```

Windows（PowerShell）：

```powershell
Copy-Item -Recurse embedded-hil-loop "$HOME\.dsh\skills\"
```

目录被监听，不用重启就会出现；确认目录里出现 `embedded-hil-loop` 这个名字再依赖它。

## 依赖

* Python 3.10+（脚本用了 `X | None` 写法）。
* Pillow —— 只有 `jprobe.py shot` 需要。
* SEGGER J-Link 软件（`JLink.exe` / `JLinkExe`）。脚本按 `--jlink` → 环境变量 `JLINK` →
  默认安装路径 → `PATH` 的顺序找。
* Arm GNU 工具链里的 `arm-none-eabi-nm`，或用 `--nm` 指定。
* 一块你**有权限**烧写和复位的板子。

`shot` 是给 STM32 LTDC 写的。换显示控制器只需要改 `cmd_shot` 里的寄存器表和像素格式解码，
其余流程不变。

## 快速开始

把 `SKILL` 设为本目录，在固件工程根目录下执行：

```bash
# 1. 板子活着吗？跑的是我以为的那版吗？
python "$SKILL/scripts/jprobe.py" --elf build/firmware.elf status s_frame_no --seconds 1

# 2. 现在屏幕长什么样？
python "$SKILL/scripts/jprobe.py" --elf build/firmware.elf shot out/before.png

# 3. 不用人，把动作做掉
python "$SKILL/scripts/synth_touch.py" --elf build/firmware.elf tap 200 418
sleep 0.5

# 4. 拿证据
python "$SKILL/scripts/jprobe.py" --elf build/firmware.elf shot out/after.png
```

输出大致是：

```
== status over 1.0s ==
  s_frame_no                      29227   delta +64   (64.0/s)
layer1 CFBAR=0x24004000 pitch=800 800x480 fmt=l8 -> out/after.png
tap (200,418) hold 120 ms
```

`delta` 是 0 就说明固件卡住了、或者你连的不是这版 —— 先解决这个，再解释其它数字。

## 什么算"做完了"

* UI 改动由**两张截图 + 一个计数器差值**证明，而不是"我把 diff 看了两遍"；
* 切页由"等它稳定后的抓屏 + 一段时间内的撕裂计数增量"证明；
* 交接文档里记了数字，下一个人不用重新推导；
* 板子最后烧的是**正式版**，并且物理触摸是好的。

## 改这个 skill 前值得知道的实现细节

* **符号从 ELF 来，不写死地址。** 静态变量也在符号表里，`arm-none-eabi-nm -n` 按地址排序输出。
  ELF 和板上固件不一致时，读到的会是"看着合理"的垃圾 —— pitfalls 里专门写了这一条。
* **写寄存器要先 halt。** 核在跑时 J-Link 的 `w4` 会静默跳过；`jprobe.py` 会 halt→写→resume。
* **抓屏跟着实时寄存器走**（CFBAR / pitch / 格式 / 行数），所以双缓冲或换调色板也不会抓错缓冲。
* **L8 默认按 RGB332 解码**（LVGL 8 位色和常见屏都是这个分法）；自定义 CLUT 用 `--palette`。
* **合成触摸需要一个"禁用符号"。** 只写缓存不够，真实驱动会把它覆盖掉；工具会先写驱动的
  "设备不存在"标志。用完物理触摸会失效到复位为止 —— 把板子交回前记得复位。

## 状态

在一个真实的 STM32H743 + LVGL 产品固件上用过：切页、滑条拖动、模态页、单次触发、
撕裂率测量、显示管线死锁。包里的脚本是工程内工具的泛化版本，两者都在硬件上跑过。

## 许可证

MIT，见 [LICENSE](LICENSE)。版权行现在是 `2026 16654`，发布前换成你的名字或 GitHub handle（一行，年份不变）。

## 来源

提炼自一个 AI 辅助的嵌入式工程（STM32H743VIT6、LTDC L8 屏、LVGL 8.3），
其完整回路是：交接 → 探针 → 复现 → 加计数器 → 修 → 抓屏 → 记录。
参考资料里保留了实测数字，方便被证伪，而不是变成教条。
