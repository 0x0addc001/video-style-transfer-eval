# 用这套 skill 评估 EchoStyle（HKUST SuperPOD 版）

**Languages:** [English](echostyle-evaluation-plan.md) | 简体中文

这是 [echostyle-evaluation-plan.md](echostyle-evaluation-plan.md) 的中文版，并补上了 HKUST
SuperPOD 的具体用法。目标是用本仓库的 skill 复现 EchoStyle（ECCV 2026,
arXiv:2606.25465）的评估表，同时保留可追溯的证据链。

## 0. 一句话结论

**推理、VBench、CSD 放 SuperPOD；manifest、诊断指标、盲评、出报告留在 MacBook。**
两边只交换三类文件：生成视频、VBench 结果 JSON、CSD 证据 JSON。

| 步骤 | 位置 | 原因 |
|---|---|---|
| 建 manifest、挑片段/风格图 | MacBook | 纯 JSON + 文件组织 |
| EchoStyle 推理 | **SuperPOD** | 14B Wan2.2 DiT，官方要求 8×80 GB GPU |
| `evaluate.py` 诊断指标 | MacBook | Farneback 光流，CPU 足够且确定性 |
| 盲评 contact sheet | MacBook | 小图人工/VLM 评审 |
| VBench（custom_input） | **SuperPOD** | AMT/MUSIQ/DINO/CLIP，CPU 上 50 条要十几小时 |
| `csd_consistency.py` | **SuperPOD**（1 GPU 即可） | CLIP ViT-L/14 前向，CPU 也能跑但慢 |
| `merge_metrics.py` / `render_report.py` | MacBook | JSON + ReportLab，无 CUDA |

### 需要准备的三类素材

1. **source 片段**：每条 3–5 秒，所有方法必须用**同一条**片段，才能做配对比较。
2. **风格条件**：EchoStyle 是**文本驱动**（中文风格 prompt），但本 skill 的 LAB 调色板指标需要一张
   `style_image`。最省事的做法是给 14 种内置风格各准备一张代表图，作为调色板锚点并在报告里说明
   “风格图为该风格的参考图，不是 EchoStyle 的输入条件”。
3. **输出视频 + 成本**：每个方法在每个 case 下的 mp4，加上 runtime 和 peak memory。

不需要的东西：VBench 官方 prompt suite（`custom_input` 模式不读它）、FID 的参考图分布（除非你确实要做 FID）。

### 规模与来源

- **规模**：EchoStyle 论文用的是 **50 个 video-instruction 对、9 种风格**。本 skill 里 2 对以上才算
  Comparative，少于 5 对时配对置信区间不稳，只能算探索性。
- **来源**（按推荐顺序）：
  - 冒烟测试：EchoStyle 仓库自带的 `assets/videos/01–11.mp4`，先跑通 3 条；
  - 正式评估：自采或公开视频（DAVIS、Videvo、Pexels 等），注意许可证与肖像权；
  - **不要用 V-Style20k 当测试集**——它是 EchoStyle 的训练数据，属于数据泄漏；
  - 风格图：EchoStyle `enable_commands.txt` 里 14 种风格的描述可作为 prompt，风格图可自备或从公开素材取。

- **泄漏控制**：在报告里写清 source 的来源、挑选规则、以及与训练数据的重叠检查结论。

> 如果某个 case 确实没有风格图，可以先用同一张图跨 case 复用（EchoStyle 的文本 prompt 才是真实条件），
> 但必须在报告里标注。需要完全无风格图的模式可以再改 `evaluate.py`，把调色板指标改为可选。

## 1. SuperPOD 上手

### 1.1 前置条件

- 网络：校园网 / `eduroam`，校外先连 [VPN](https://itso.hkust.edu.hk/services/cyber-security/vpn)。
- 账号：SuperPOD 账号需要 **PI 担保申请**（学生请导师提交），用户名密码与 HKUST 账号一致。
- 双因子：密码登录需要先注册 [Duo MFA](https://itso.hkust.edu.hk/services/cyber-security/duo)；推荐改用 SSH key 免密。

### 1.2 登录

```bash
ssh <hkust_username>@superpod.ust.hk     # 不带 @ust.hk
```

配免密（推荐，MacBook 上已有 `~/.ssh/id_ed25519.pub`）：

```bash
ssh-copy-id -i ~/.ssh/id_ed25519.pub <hkust_username>@superpod.ust.hk
```

登录节点是 `slogin-*`，**只能改文件、编译、提交作业、传数据**，跑重活会被管理员杀掉。

### 1.3 先确认自己的账户和分区

```bash
sacctmgr show user $USER withassoc   # 看 Def Acct 和可用 Partition
sinfo -o "%20P %5D %15G %10l"        # 看分区、节点数、GPU 类型、时限
```

`--account` 必须和 `--partition` 配对，否则 `sbatch` 会报
`Invalid account or account/partition combination specified`。

### 1.4 分区规则（重要）

| 分区 | 用途 | 单作业 GPU | 时限 | 单用户并发 |
|---|---|---|---|---|
| `normal` | 正式 GPU 任务 | 1–96（即 1–12 节点） | 3 天 | 8 个运行 / 10 个排队 |
| `preempt` | 抢占空闲资源 | 1–96 | 理论 3 天，但**空闲资源被收回时 1 小时后可能被杀** | 8 个运行 |
| `cpu` | 预处理 | 无 GPU | 12 小时 | 28 个 |

- 1 张 GPU 默认配 14 核 / 28 线程 / 224 GB 内存，**只写 `--gpus-per-node` 和 `--nodes` 即可**，不要手写核数和内存。
- GPU 是 **H800 80 GB**，不是 EchoStyle 论文里的 A100。显存够，但 NVLink 带宽不同，**运行时间不能和论文直接比**；报告里要写清硬件。
- 交互式会话（`srun --pty`）最长 8 小时；正式长任务用 `sbatch`。
- `normal` 申请 GPU 越多优先级越高；`preempt` 不要放会跑几小时的任务。

### 1.5 存储

| 路径 | 用途 | 注意 |
|---|---|---|
| `/home/<user>` | 代码、conda 环境、配置 | 有配额（见 welcome email），有备份 |
| `/scratch/<group>` | 5 TB 组配额，放模型权重、数据集、输出 | **30 天不访问自动清理**，不是备份 |
| `/project/<group>` | 组共享长期数据 | 见 welcome email |

EchoStyle 的 Wan2.2 权重、HuggingFace 缓存、VBench 模型都放 `/scratch/<group>`，
并在作业里显式设 `HF_HOME`、`MODELSCOPE_CACHE`，否则会写爆 home。
注意：**`cpu` 分区看不到 `/scratch`**。

### 1.6 软件环境

SuperPOD 推荐用容器（Enroot/Pyxis），也可以用 Spack 模块：

```bash
module purge
source /opt/shared/.spack-edge/dist/bin/setup-env.sh -y
module avail
module load anaconda3/2025
```

EchoStyle 需要 Python ≥3.10、torch ≥2.4（cu121）、flash-attn，模块里的 Python 版本不一定匹配，
所以**用 conda 自建环境**最稳（装在 `/home` 或 `/project`，不要装 `/scratch`，会被清）。

## 2. 环境准备（只做一次）

```bash
ssh <user>@superpod.ust.hk
mkdir -p /scratch/<group>/echostyle && cd /scratch/<group>/echostyle

git clone https://github.com/HKUST-C4G/EchoStyle.git
module purge
source /opt/shared/.spack-edge/dist/bin/setup-env.sh -y
conda create -y -p /home/<user>/envs/echostyle python=3.10
conda activate /home/<user>/envs/echostyle

pip install torch==2.4.0 torchvision==0.19.0 --index-url https://download.pytorch.org/whl/cu121
pip install flash-attn --no-build-isolation
pip install -e EchoStyle

export HF_HOME=/scratch/<group>/hf
export MODELSCOPE_CACHE=/scratch/<group>/modelscope
# 下载 Wan2.2-I2V-14B、Wan2.2-Lightning、EchoStyle 双 LoRA 到 /scratch/<group>/models
```

> flash-attn 要编译，Hopper（H800）建议用 2.5 以上版本；编译前先 `module load cuda` 对应版本，
> 并在**计算节点**上编译（`srun -p normal --gpus=1 --pty bash`），登录节点没有 CUDA。

## 3. 推理作业模板（8 GPU）

先把 50 条 source 视频和 manifest 传上去（见第 5 节），然后在 `EchoStyle/` 下写
`scripts/eval_superpod.sbatch`：

```bash
#!/bin/bash
#SBATCH --job-name=echostyle-eval
#SBATCH --account=<ACCOUNT>
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --gpus-per-node=8
#SBATCH --time=08:00:00
#SBATCH --output=/scratch/<group>/echostyle/logs/eval-%j.out

set -euo pipefail
source /opt/shared/.spack-edge/dist/bin/setup-env.sh -y
conda activate /home/<user>/envs/echostyle

export HF_HOME=/scratch/<group>/hf
export MODELSCOPE_CACHE=/scratch/<group>/modelscope
cd /scratch/<group>/echostyle/EchoStyle

# scripts/eval.sh 内部已用 torchrun --nproc_per_node 8
bash scripts/eval.sh
```

提交与监控：

```bash
mkdir -p /scratch/<group>/echostyle/logs
sbatch scripts/eval_superpod.sbatch
squeue -u $USER
tail -f /scratch/<group>/echostyle/logs/eval-<jobid>.out
```

先跑通一条视频再上 50 条：

```bash
srun -p normal --gpus=8 --time=01:00:00 --pty bash   # 交互调试，≤8h
```

`--gpus=8` 会占满一整节点；调试完成后 `exit` 释放。

## 4. VBench 与 CSD 作业模板（1 GPU）

VBench 和 CSD 都不需要 8 卡，用 1 卡即可，但**同样要在计算节点上跑**。

```bash
#!/bin/bash
#SBATCH --job-name=echostyle-metrics
#SBATCH --account=<ACCOUNT>
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --gpus-per-node=1
#SBATCH --time=06:00:00
#SBATCH --output=/scratch/<group>/echostyle/logs/metrics-%j.out

set -euo pipefail
source /opt/shared/.spack-edge/dist/bin/setup-env.sh -y
conda activate /home/<user>/envs/echostyle
cd /scratch/<group>/echostyle/evaluation

export HF_HOME=/scratch/<group>/hf

for dim in motion_smoothness imaging_quality aesthetic_quality \
           subject_consistency background_consistency temporal_flickering dynamic_degree; do
  python -m vbench.cli evaluate --videos_path outputs/echostyle \
    --dimension "$dim" --mode=custom_input
done

python /scratch/<group>/echostyle/video-style-transfer-eval/scripts/vbench_import.py \
  --manifest manifest.json --results vbench_results \
  --output evidence/vbench.json

python /scratch/<group>/echostyle/video-style-transfer-eval/scripts/csd_consistency.py \
  --manifest manifest.json --output evidence/csd.json \
  --checkpoint yuxi-liu-wired/CSD --device cuda --max-frames 32
```

两个注意点：

- **manifest 里的相对路径**在服务器和本地要保持同构（`evaluation/manifest.json` +
  `evaluation/outputs/<method>/<case>.mp4`），这样回传后证据的 case/method ID 能对上。
- CSD 第一次会从 HuggingFace 下载 CLIP ViT-L/14（约 1.7 GB），确保 `HF_HOME` 在 scratch；
  服务器若不能直连 HF，先在有网的机器下载好再 `rsync` 上去。

## 5. 数据搬运（rsync，登录节点执行）

```bash
# 本地 → 服务器：只传 source/style 和 manifest
rsync -av --progress evaluation/ <user>@superpod.ust.hk:/scratch/<group>/echostyle/evaluation/

# 服务器 → 本地：只回传生成视频 + 两个证据 JSON
rsync -av --progress \
  <user>@superpod.ust.hk:/scratch/<group>/echostyle/evaluation/outputs/ \
  evaluation/outputs/
rsync -av --progress \
  <user>@superpod.ust.hk:/scratch/<group>/echostyle/evaluation/evidence/ \
  evaluation/evidence/
```

大文件不要放 `/home`；`/scratch` 30 天不访问会被清，重要结果及时拉回本地。

## 6. 回本地出报告

```bash
python scripts/evaluate.py --manifest evaluation/manifest.json \
  --output-dir evaluation_run --blind

python scripts/validate_review.py \
  --review reviews/*.json \
  --blind-map evaluation_run/review_packet/blind_map.json

python scripts/merge_metrics.py \
  --metrics evaluation_run/metrics.json \
  --evidence evaluation/evidence/csd.json evaluation/evidence/vbench.json \
  --output evaluation_run/metrics_merged.json

python scripts/render_report.py \
  --metrics evaluation_run/metrics_merged.json \
  --review evaluation_run/review_packet/validated_reviews.json \
  --output-dir evaluation_report \
  --language both --primary echostyle --baseline <baseline_id>
```

## 7. 与 EchoStyle Table 1 的对应

| EchoStyle 列 | 本 skill | 说明 |
|---|---|---|
| Style Similarity | `csd_s` 或盲评 | EchoStyle 用 Gemini-3-pro 成对胜率，需要 API，不能伪装成 skill 算的 |
| Style Consis. | `csd_s` | 同一 CSD 模型族，首帧 vs 后续帧 |
| Motion Smooth. | `vbench_motion_smoothness` | VBench 维度 |
| Imaging Qual. | `vbench_imaging_quality` | VBench（MUSIQ） |
| Static Qual. | `vbench_subject_consistency` + `vbench_background_consistency` | VBench 近似，不是 Gemini 分数 |
| Dynamic Qual. | `vbench_dynamic_degree` | 受源视频运动量约束，只能同运动量比较 |
| Aesthetic Qual. | `vbench_aesthetic_quality` | 摄影美学先验，会压低水墨/油画风格 |
| Human preference | 盲评 rubric + validated reviews | 五个维度分开报，不要合成单一总分 |

## 8. 计费与常见坑

- `normal`/`preempt` 按 **GPU·小时计费**，`cpu` 免费；先用 `cpu` 或 1 卡调通流程再上 8 卡。
- `normal` 单作业上限 3 天；超长视频请分片或缩短评估窗口。
- `preempt` 1 小时后可能被无预警杀掉，**不要**放推理长任务；被杀的作业不会自动重跑。
- 登录节点跑 python/torch 会被杀；一律 `srun`/`sbatch`。
- 交互会话 8 小时上限，记得 `exit`。
- `cpu` 分区看不到 `/scratch`，需要 `/scratch` 的任务不要丢到 cpu 分区。
- 同一个 `--account` 下并发 8 个作业，超过会排队；批量跑 VBench 时合并成一个作业循环所有维度，别开七个作业。
- 报告里要记录 H800 80 GB、驱动/CUDA、torch 版本，以及 EchoStyle 的 commit / LoRA checkpoint。

## 9. 预算与冒烟测试

SuperPOD 共 440 张 H800，按 **HKD 0.2 / GPU-分钟**（= **HKD 12 / GPU-小时**）计费，
每位同学有 **HKD 2,000** 额度。换算下来：

- 8 卡满节点跑 1 小时 = **HKD 96**
- 2,000 额度 = 10,000 GPU-分钟 = **≈167 GPU-小时** ≈ **20.8 个「8 卡·小时」**

### 成本估算

| 阶段 | 用量 | 估算费用 |
|---|---|---|
| 本地冒烟（demo 3 条，纯诊断） | 0 GPU | HKD 0 |
| 服务器冒烟：1 条片段，8 卡约 10 分钟 | 80 GPU-分钟 | ≈ HKD 16 |
| 单卡跑 VBench 七维 + CSD（50 条） | 1–2 GPU-小时 | ≈ HKD 12–24 |
| 全量 50 条（2.5 分钟/条） | ≈1000 GPU-分钟 | ≈ HKD 200 |
| 全量 50 条（6 分钟/条） | ≈2400 GPU-分钟 | ≈ HKD 480 |
| Lightning（10 步）冒烟 | 约为标准模式 1/5 | ≈ HKD 3–5/条 |

也就是说 2,000 额度够 **4–10 次**完整评估，但前提是先量出“一条片段实际要多久”。
第一次务必只跑 1 条并记录耗时，再决定是全量还是换 Lightning 档。

### 冒烟三步

1. **本地**（1 分钟、0 元）：验证 skill 本身没问题

   ```bash
   python scripts/evaluate.py \
     --manifest examples/sample_report/demo_run/manifest.json \
     --output-dir /tmp/vst_smoke/run --blind
   python scripts/render_report.py --metrics /tmp/vst_smoke/run/metrics.json \
     --output-dir /tmp/vst_smoke/report --language en --status Exploratory
   ```

2. **服务器**（约 HKD 16）：1 条片段 + 8 卡，确认权重、LoRA、输出视频都能出

   ```bash
   srun -p normal --gpus=8 --time=00:30:00 --pty bash
   # 进入后激活环境，把 test_10.json 只留 1 条，执行 bash scripts/eval.sh
   ```

3. **单卡指标**：对这条输出跑 VBench 一个维度 + `csd_consistency.py`，
   再用 `merge_metrics.py` 在本地合并，确认证据链路通。

### 让 agent 直接驱动服务器

`superpod.ust.hk:22` 从这台 Mac 是可达的，目前只缺授权。把本机公钥装上去一次即可：

```bash
# 本机执行（会要一次密码 + Duo，交互式，只能你自己做）
ssh-copy-id -i ~/.ssh/id_ed25519.pub <user>@superpod.ust.hk

# 装好后验证
ssh <user>@superpod.ust.hk 'hostname; sacctmgr show user $USER withassoc'
```

之后 agent 就能用非交互 ssh 帮你提交、轮询、拉日志（密钥登录不需要 Duo）。
注意：不要把密码贴进对话。
