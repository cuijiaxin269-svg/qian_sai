APP_TITLE = "嵌入式测试系统上位机（初版）"
DEFAULT_BAUDRATE = 115200
DEFAULT_DATA_SAVE_DIR = r"D:\qian_sai\data_save"
BAUDRATES = [9600, 57600, 115200, 230400]

ROUTES = [
    ("Ciss 测量回路", "CISS_MEAS"),
    ("Coss 测量回路", "COSS_MEAS"),
    ("Crss 测量回路", "CRSS_MEAS"),
    ("Ciss 放电回路", "CISS_DISCHARGE"),
    ("Coss 放电回路", "COSS_DISCHARGE"),
    ("Crss 放电回路", "CRSS_DISCHARGE"),
    ("全部断开 / 安全状态", "SAFE_OPEN"),
]
