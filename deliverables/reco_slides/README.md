# ReCo-Bench 汇报幻灯片（LaTeX / Beamer）

由 `scripts/build_eval_beamer.py` 从两个评估目录生成，XeTeX + Tectonic 编译。

| 文件 | 内容 |
|---|---|
| `reco_2style_10sample.pdf` | 10 视频 × 2 风格（20 对） |
| `reco_12style_5sample.pdf` | 5 视频 × 12 风格（60 对） |

重新生成：

```bash
python scripts/build_eval_beamer.py
cd deliverables/reco_slides
tectonic -X compile reco_2style_10sample.tex
tectonic -X compile reco_12style_5sample.tex
```

数据来源：`evaluation_run/reco_2style_10sample` 与
`evaluation_run/reco_12style_5sample`（metrics、validated reviews、contact sheets）。

已知缺口：峰值显存尚未采样；VBench 七维尚未运行。运行时长为推理日志中相邻
`Saved to` 时间戳之差（60 对均值 266.1 s）。
