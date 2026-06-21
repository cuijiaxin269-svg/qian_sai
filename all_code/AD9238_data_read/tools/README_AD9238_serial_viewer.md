# AD9238 串口上位机脚本

脚本：

```text
tools/ad9238_serial_viewer.py
```

依赖：

```powershell
pip install pyserial matplotlib
```

先查看串口：

```powershell
python tools\ad9238_serial_viewer.py --list-ports
```

没有连接串口时，可以先预览双通道界面：

```powershell
python tools\ad9238_serial_viewer.py --demo
```

生成界面预览图片：

```powershell
python tools\ad9238_serial_viewer.py --demo --save-plot build\ad9238_viewer_demo.png
```

实时接收并显示波形：

```powershell
python tools\ad9238_serial_viewer.py -p COM5
```

只接收一帧并保存 CSV：

```powershell
python tools\ad9238_serial_viewer.py -p COM5 --once --save-csv
```

默认参数与 STM32 代码一致：

```text
115200 baud, 8N1
帧头：AD9238_FRAME_BEGIN
数据：index,ch_a,ch_b
帧尾：AD9238_FRAME_END
```

如果 STM32 里改了每路采样率，运行时同步指定：

```powershell
python tools\ad9238_serial_viewer.py -p COM5 --sample-rate 1600000
```
