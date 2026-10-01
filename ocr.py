# -*- coding: utf-8 -*-
"""离线 OCR：RapidOCR 封装，裁剪识别框 → 小字放大 → 拼接文本"""
import logging

import cv2

log = logging.getLogger("yihuan")


class OCREngine:
    def __init__(self, config):
        logging.getLogger("RapidOCR").setLevel(logging.ERROR)
        from rapidocr import RapidOCR
        # log_level=error：关闭模型加载/空检测等 INFO、WARNING 噪声（保证静默）
        self.engine = RapidOCR(params={"Global.log_level": "error"})
        ocr_config = config.get("ocr", {})
        self.upscale_height = int(ocr_config.get("upscale_height", 40))
        self.upscale_scale = int(ocr_config.get("upscale_scale", 3))

    def read(self, image, region):
        """识别矩形区域 [[x1,y1],[x2,y2]] 内的全部文本，返回拼接字符串"""
        (x1, y1), (x2, y2) = region
        height, width = image.shape[:2]
        x1, y1 = max(int(x1), 0), max(int(y1), 0)
        x2, y2 = min(int(x2), width), min(int(y2), height)
        if x2 <= x1 or y2 <= y1:
            return ""
        crop = image[y1:y2, x1:x2]
        if crop.shape[0] < self.upscale_height:
            crop = cv2.resize(crop, None, fx=self.upscale_scale, fy=self.upscale_scale,
                              interpolation=cv2.INTER_CUBIC)
        try:
            result = self.engine(crop)
        except Exception as error:
            log.error("OCR 识别失败: %s", error)
            return ""
        texts = getattr(result, "txts", None) or ()
        return "".join(str(text) for text in texts).replace(" ", "")
