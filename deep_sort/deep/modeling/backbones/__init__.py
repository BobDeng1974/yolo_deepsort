# encoding: utf-8
"""
@author:  liaoxingyu
@contact: sherlockliao01@gmail.com
"""

from .build import build_backbone, BACKBONE_REGISTRY

from .resnet import build_resnet_backbone
from .darknet import build_darknet_backbone
from .r18x import build_r18x_backbone