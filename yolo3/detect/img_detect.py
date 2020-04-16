import datetime
import logging
import os
import random
import time

import cv2
import matplotlib.pyplot as plt
import numpy as np
import torch
import torchvision.transforms as transforms
from PIL import Image
from matplotlib import patches
from matplotlib.ticker import NullLocator
from torch.autograd import Variable

from yolo3.dataset.dataset import pad_to_square
from yolo3.utils.helper import load_classes
from yolo3.utils.model_build import non_max_suppression, rescale_boxes


class ImageDetector:
    """图像检测器，只检测单张图片"""

    def __init__(self, model, class_path, thickness=2,
                 conf_thres=0.5,
                 nms_thres=0.4):
        self.model = model
        self.model.eval()
        self.classes = load_classes(class_path)
        self.num_classes = len(self.classes)
        self.thickness = thickness
        self.conf_thres = conf_thres
        self.nms_thres = nms_thres
        self.__to_tensor = transforms.ToTensor()

    def detect(self, img):

        Tensor = torch.cuda.FloatTensor if torch.cuda.is_available() else torch.FloatTensor

        # 按比例缩放
        h, w, _ = img.shape
        if w > h:
            img = cv2.resize(img, (self.model.img_size, int(h * self.model.img_size / w)))
        else:
            img = cv2.resize(img, (int(w * self.model.img_size / h), self.model.img_size))

        image = self.__to_tensor(img).type(Tensor)

        if len(image.shape) != 3:
            image = image.unsqueeze(0)
            image = image.expand((3, image.shape[1:]))

        image, _ = pad_to_square(image, 0)

        # Add batch dimension
        image = image.unsqueeze(0)

        prev_time = time.time()
        with torch.no_grad():
            detections = self.model(image)
            detections = non_max_suppression(detections, self.conf_thres, self.nms_thres)
            detections = detections[0]

        current_time = time.time()
        inference_time = datetime.timedelta(seconds=current_time - prev_time)
        logging.info("\t Inference time: %s" % inference_time)

        if detections is not None:
            detections = rescale_boxes(detections, self.model.img_size, (h, w))

        return detections


class ImageFolderDetector:
    """图像文件夹检测器，检测一个文件夹中的所有图像"""

    def __init__(self, model, class_path):
        self.model = model.eval()
        self.classes = load_classes(class_path)

    def detect(self, dataloader, output_dir, conf_thres=0.8, nms_thres=0.4):

        Tensor = torch.cuda.FloatTensor if torch.cuda.is_available() else torch.FloatTensor

        imgs = []  # Stores image paths
        img_detections = []  # Stores detections for each image index

        prev_time = time.time()
        for batch_i, (img_paths, input_imgs) in enumerate(dataloader):
            input_imgs = Variable(input_imgs.type(Tensor))

            with torch.no_grad():
                detections = self.model(input_imgs)
                detections = non_max_suppression(detections, conf_thres, nms_thres)

            current_time = time.time()
            inference_time = datetime.timedelta(seconds=current_time - prev_time)
            prev_time = current_time
            logging.info("\t+ Batch %d, Inference time: %s" % (batch_i, inference_time))

            imgs.extend(img_paths)
            img_detections.extend(detections)

        # Bounding-box colors
        colors = plt.get_cmap("tab20b").colors

        logging.info("\nSaving images:")

        for img_i, (path, detections) in enumerate(zip(imgs, img_detections)):

            logging.info("(%d) Image: '%s'" % (img_i, path))
            # Create plot
            img = np.array(Image.open(path))
            plt.figure()
            fig, ax = plt.subplots(1)
            ax.imshow(img)

            if detections is not None:
                detections = rescale_boxes(detections, self.model.img_size, img.shape[:2])
                unique_labels = detections[:, -1].cpu().unique()
                n_cls_preds = len(unique_labels)
                bbox_colors = random.sample(colors, n_cls_preds)
                for x1, y1, x2, y2, conf, cls_conf, cls_pred in detections:
                    logging.info("\t+ Label: %s, Conf: %.5f" % (self.classes[int(cls_pred)], cls_conf.item()))

                    box_w = x2 - x1
                    box_h = y2 - y1

                    color = bbox_colors[int(np.where(unique_labels == int(cls_pred))[0])]
                    bbox = patches.Rectangle((x1, y1), box_w, box_h, linewidth=2, edgecolor=color, facecolor="none")
                    # Add the bbox to the plot
                    ax.add_patch(bbox)
                    # Add label
                    plt.text(x1, y1, s=self.classes[int(cls_pred)],
                             color="white",
                             verticalalignment="top",
                             bbox={"color": color, "pad": 0})

            # Save generated image with detections
            plt.axis("off")
            plt.gca().xaxis.set_major_locator(NullLocator())
            plt.gca().yaxis.set_major_locator(NullLocator())

            filename = os.path.basename(path).split(".")[0]
            output_path = os.path.join(output_dir, filename + ".png")
            plt.savefig(output_path, bbox_inches="tight", pad_inches=0.0)
            plt.close()
