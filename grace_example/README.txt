GRACE mascon 海平面指纹示例数据
============================================================

网格分辨率: 1°（经度 360 × 纬度 180）
质量变化单位: **米**当量水高（原 mascon 为 cm，已除以 100）
run 时载荷网格间隔参数 dlon/dlat 应填 1

载荷文件（每行：经度 纬度 水当量高度(m)）:
  load_grace_t0001_1deg.txt                GRACE t0001 单历元
  load_grace_trend_1deg.txt                趋势 t0001~t0005

love_numbers: Wang et al. (2012) PREM-LLNs-complete.dat 的 h、k 列
land.fcn.1_deg: Natural Earth 110m 陆地多边形栅格化（1=陆地，0=海洋）

GRACE 来源: CSR GRACE/GRACE-FO RL06.3 mascon (all-corrections),
           lwe_thickness, 0.25°, 行序自南向北
