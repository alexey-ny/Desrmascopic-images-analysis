# -*- coding: utf-8 -*-
"""
Created on Mon Nov 20 22:34:59 2023

@author: alex
"""

import os
# os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
# os.environ["CUDA_VISIBLE_DEVICES"] = "0"
# os.environ["CUDA_VISIBLE_DEVICES"] = "1"

import copy
import random
import warnings
warnings.filterwarnings('ignore')
from datetime import datetime
import cv2
import numpy as np
import pandas as pd 
from imgaug import augmenters as iaa
import math
# import logging
from sklearn.model_selection import KFold
from sklearn.metrics import roc_auc_score, auc #, roc_curve, precision_recall_curve
from sklearn.metrics import average_precision_score, confusion_matrix
# , f1_score, precision_score, classification_report
from sklearn.utils import shuffle
from sklearn.metrics import precision_recall_fscore_support, precision_recall_curve
from sklearn.preprocessing import MinMaxScaler
# from sklearn.metrics import RocCurveDisplay
# from sklearn import metrics
# import matplotlib.pyplot as plt
# import matplotlib.colors as mcolors
# import keras
import tensorflow as tf
from tensorflow.keras.layers import Input, GlobalAveragePooling2D, Dropout, Dense
from tensorflow.keras.callbacks import TensorBoard, CSVLogger, ModelCheckpoint
import tensorflow.keras.backend as K
from keras.metrics import PrecisionAtRecall

from tensorflow.keras.applications.resnet_v2 import ResNet50V2, ResNet101V2, ResNet152V2
# from tensorflow.keras.applications.densenet import DenseNet121
from tensorflow.keras.applications.efficientnet_v2 import EfficientNetV2B0, \
    EfficientNetV2B1, EfficientNetV2B2
# import tensorflow.keras.applications.efficientnet_v2.preprocess_input as eff_v2_preprocess    
from tensorflow.keras.applications.efficientnet import EfficientNetB0,\
    EfficientNetB1, EfficientNetB2, EfficientNetB3, EfficientNetB4, \
    EfficientNetB5, EfficientNetB6, EfficientNetB7
# import tensorflow.keras.applications.efficientnet.preprocess_input as eff_v1_preprocess    
from tensorflow.keras import mixed_precision
# import tensorflow_addons as tfa
# from tqdm import tqdm
# import numba
from numba import njit

import pickle
import simplejpeg 

from logging_utils import *
# from logging_utils import loggers
from logging_utils import myLogger, print_log, close_loggers 

from plot_utils import plot_mean_ROC, plot_mean_PR


n_folds = 5
DEVICE = "GPU"
MULTI = False

SEED = 1970
random.seed(SEED)
tf.random.set_seed(SEED)
np.random.seed(SEED)
os.environ['PYTHONHASHSEED'] = str(SEED)

EFNS = [EfficientNetB0, EfficientNetB1, EfficientNetB2, EfficientNetB3, 
        EfficientNetB4, EfficientNetB5, EfficientNetB6, EfficientNetB7,
        EfficientNetV2B0, EfficientNetV2B1, EfficientNetV2B2,
        ResNet50V2, ResNet101V2, ResNet152V2]
nets_names = ['v1b0', 'v1b1', 'v1b2', 'v1b3', 'v1b4', 'v1b5', 'v1b6', 'v1b7',
              'v2b0', 'v2b1', 'v2b2', 'resnet50v2', 'resnet101v2', 'resnet152v2']

params = {
    # 'IMG_SIZES' :   [128],
    # 'IMG_SIZES' :   256, 
    'IMG_SIZES' :  512,
    # 'EFF_NETS' :    9,
    'EFF_NETS' :    10,
    # 'EFF_NETS' :    [11],
    'BATCH_SIZES' : 64,
    # 'BATCH_SIZES' : 128,
    # 'BATCH_SIZES' : 32,
    # 'BATCH_SIZES' : 16,
    # 'EPOCHS' : 11,
    'EPOCHS' : 7,
    # 'EPOCHS' : 1,
    # number of times to duplicate the malignant samples, to use with augmentation to balance the classes
    'MAL_UPSAMPLE' : 5, 
    # 'MAL_UPSAMPLE' : 20, 
    # test time augmentation steps
    'TTA' : 0,
    # 'TTA' : 10,
    'FOCAL_LOSS' : False,
    # possible values are 'RGB', 'HSV' and 'YCrCb'
    # 'COLOR_SPACE' : 'RGB' ,
    'COLOR_SPACE' : 'HSV' ,
    'COMPUTE_RGB' : True, # shall we train the model in RGB space for comparison
    # 'COMPUTE_RGB' : False, # shall we train the model in RGB space for comparison
    'DROP_LUM_CH' : False, # if we should drop Luminosity channel in HSV of YCrCb spaces
    '4TH_CHANNEL' : 'EI' , # either EI or MI, to estimate if one is more important than the other
    'LR_START' : 0.001,
    # 'LR_MAX'   : 0.009,
    # 'LR_MIN'   : 0.00005,
    
    # 'LR_START'  : 0.0005,
    'LR_MAX'    : 0.0015,
    'LR_MIN'    : 0.000001,
    'LR_RAMP_EP' : 10,
    # 'LR_RAMP_EP' : 5,
    # 'LR_SUS_EP' : 0, # cycle step
    'LR_SUS_EP' : 3, # cycle step
    'LR_DECAY' : 0.8,
    # number of channels, to use additional channels/information besides RGB
    # 'N_CHANNELS' : 3
    'N_CHANNELS' : 5
    }


tb_logs = 'logs_tb'
model_logs = './logs_model/'
inferences = './inferences/'
data_path = './data/'

mean_metrics = 'mean_metrics.csv'
mean_metrics_cols = ['date', 'model', 'image_size', 'batch_size', 'channel', 'test_set','roc_auc', 'pr_auc', 'f1', 'precision', 'recall']

# train_image_folder_path = "./jpeg/231114_all_data_ISIC/512/"
# test_image_folder_path = "./jpeg/231114_all_data_ISIC/512/"     # 15% of all available ISIC data
train_image_folder_path = "./jpeg/231115_all_data_ISIC/512/"
test_image_folder_path = "./jpeg/231115_all_data_ISIC/512/"     # 15% of all available ISIC data
test_Kaggle_image_folder_path = "./jpeg/test/1024/"             # online Kaggle test set for submision to check AUC score
test_no_lesion_id_image_folder_path = "./jpeg/231115_all_data_ISIC/512/"       # additional local test set of data with no patient_id and no lesion_id, subset of full ISIC dataset
# test_no_lesion_id_image_folder_path = "./jpeg/231114_all_data_ISIC/512/"       # additional local test set of data with no patient_id and no lesion_id, subset of full ISIC dataset

policy = mixed_precision.Policy('mixed_float16')
mixed_precision.set_global_policy(policy)

df_mean_metrics = pd.read_csv(f'{data_path}/mean_metrics.csv')

datetime_now = datetime.now().strftime('%Y%m%d')
main_logger = myLogger('main', f"{model_logs}{datetime_now}-{nets_names[params['EFF_NETS']]}_img{str(params['IMG_SIZES'])}-main.log")
res_logger = myLogger('result', f"{model_logs}{datetime_now}-{nets_names[params['EFF_NETS']]}_img{str(params['IMG_SIZES'])}-results.log", False)

print_log('*' * 80, [main_logger])
print_log('Begin logging', [main_logger])
print_log('tensorflow version:' + str(tf.__version__), [main_logger])

print_log('Compute dtype: %s' % policy.compute_dtype, [main_logger])
print_log('Variable dtype: %s' % policy.variable_dtype, [main_logger])

gpu_devices = tf.config.list_logical_devices('GPU')
if gpu_devices:
    for gpu_device in gpu_devices:
        print_log('device available:' + str(gpu_device), [main_logger])

if DEVICE != "TPU":
    if MULTI:
        print_log("Using default strategy for multiple GPUs", [main_logger])
        strategy = tf.distribute.MirroredStrategy(gpu_devices)
    else:
        print_log("Using default strategy for CPU and single GPU", [main_logger])
        strategy = tf.distribute.get_strategy()
   
AUTO = tf.data.experimental.AUTOTUNE
REPLICAS = strategy.num_replicas_in_sync
print_log(f'Number of Replicas Used: {REPLICAS}', [main_logger])

pd.set_option('display.max_columns', None)

df_train = pd.read_csv(data_path + '231120_train.csv')
df_test = pd.read_csv(data_path + '231120_test.csv')                            # 15% of all available ISIC data
df_test_Kaggle = pd.read_csv(data_path + 'test.csv')                            # online Kaggle test set for submision to check AUC score
df_test_no_lesion_id = pd.read_csv(data_path + '231120_no_lesion_ID.csv')       # additional local test set of data with no patient_id and no lesion_id, subset of full ISIC dataset

trn_set = df_train.copy()
mals_2020 = np.array(trn_set.loc[trn_set.target == 1].index).astype('int32')
idx_trn = np.array(trn_set.index).astype('int32')
for m in range(params['MAL_UPSAMPLE']):
    idx_trn = np.concatenate((idx_trn, mals_2020))   
np.random.shuffle(idx_trn)

train_ext = trn_set.loc[idx_trn]
train_set = train_ext.copy().reset_index(drop = True)

train_IP_set = train_set['patient_id'].unique()

y_test = df_test['target']
df_test.drop(columns = ['target'], inplace = True, axis = 1)
print_log(f'Local test set (15% full ISIC) target classes counts: \n{y_test.value_counts()}', [main_logger])

y_test_no_lesion = df_test_no_lesion_id['target']
df_test_no_lesion_id.drop(columns = ['target'], inplace = True, axis = 1)
print_log(f'Local test set (both lesion_id and patient_id are unknown), target classes counts: \n{y_test_no_lesion.value_counts()}', [main_logger])

y_train_set = train_set['target']
print_log(f'Full train set with {params["MAL_UPSAMPLE"]} upsamplings, target classes counts: \n{y_train_set.value_counts()}', [main_logger])

print_log(f"Color space: {params['COLOR_SPACE']}; 4th channel: {params['4TH_CHANNEL']}; Drop luminosity channel: {params['DROP_LUM_CH']}", [main_logger])

    
def get_lr_callback(batch_size=8):
    lr_start   = params['LR_START']
    lr_max     = params['LR_MAX']
    lr_min     = params['LR_MIN']
    lr_ramp_ep = params['LR_RAMP_EP']
    lr_sus_ep  = params['LR_SUS_EP']
    lr_decay   = params['LR_DECAY']  
    def lrfn_simple(epoch):
        cur_step = epoch % lr_sus_ep  
        cur_cycle = int(epoch / lr_sus_ep)
        step_dec = (lr_start - lr_min) / lr_sus_ep
        step_decay_decrease = (lr_decay ** (1 / (cur_step + 1))) / (2 * 1000)
        cycle_decay_decrease = (lr_decay ** (1 / (cur_cycle + 1))) / (2* 1000)       
        lr = lr_start - step_dec * cur_step + step_decay_decrease - cycle_decay_decrease
        tf.summary.scalar('Learning Rate', data = lr, step = epoch)
        return lr

    def lrfn(epoch):
        if epoch < lr_ramp_ep:
            # lr = (lr_max - lr_start) / (lr_ramp_ep * (epoch + 1)) + lr_start
            lr = (lr_max - lr_start) / lr_ramp_ep * epoch + lr_start        
        elif epoch < lr_ramp_ep + lr_sus_ep:
            lr = lr_max
        else:
            # lr = (lr_max - lr_min) * lr_decay**(epoch - lr_ramp_ep - lr_sus_ep) + lr_min
            lr = (lr_max - lr_min) * lr_decay**(1 / (epoch - lr_ramp_ep - lr_sus_ep + 0.000000001)) + lr_min
            print(f'Epoch {(epoch - lr_ramp_ep - lr_sus_ep):2.4}, exp = {(epoch - lr_ramp_ep - lr_sus_ep):2.4}, decay = {(lr_decay**(1 / (epoch - lr_ramp_ep - lr_sus_ep + 0.000000001))):2.4 }' )
        tf.summary.scalar('Learning Rate', data = lr, step = epoch)
        return lr

    lr_callback = tf.keras.callbacks.LearningRateScheduler(lrfn_simple, verbose=False)
    # lr_callback = tf.keras.callbacks.LearningRateScheduler(lrfn, verbose=False)
    return lr_callback


def get_lr_callback_kaggle(batch_size=8):
    lr_start   = 0.000005
    lr_max     = 0.00000125 * REPLICAS * batch_size
    lr_min     = 0.000001
    lr_ramp_ep = 5
    lr_sus_ep  = 0
    lr_decay   = 0.8
   
    def lrfn(epoch):
        if epoch < lr_ramp_ep:
            lr = (lr_max - lr_start) / lr_ramp_ep * epoch + lr_start
            
        elif epoch < lr_ramp_ep + lr_sus_ep:
            lr = lr_max
            
        else:
            lr = (lr_max - lr_min) * lr_decay**(epoch - lr_ramp_ep - lr_sus_ep) + lr_min
            
        return lr

    lr_callback = tf.keras.callbacks.LearningRateScheduler(lrfn, verbose=False)
    return lr_callback

def Focal_Loss(y_true, y_pred, alpha = 0.25, gamma = 2, weight = 5):
    """
    Binary Cross Entropy modified to work better with imbalanced datasets
    Parameters
    ----------
    y_true : array, float
        Target.
    y_pred : array, float
        Predicted labels.
    alpha : float, optional
        The default is 0.25.
    gamma : float, optional
        The default is 2.
    weight : float, optional
        The default is 5.
    Returns
    -------
    float
        Computed loss.
    """
    y_true = K.flatten(tf.cast(y_true, tf.float32))
    y_pred = K.flatten(tf.cast(y_pred, tf.float32))

    BCE = K.binary_crossentropy(y_true, y_pred)
    BCE_EXP = K.exp(-BCE)
    alpha = alpha*y_true+(1-alpha)*(1-y_true)
    focal_loss = K.mean(alpha * K.pow((1-BCE_EXP), gamma) * BCE)

    return BCE + weight * focal_loss


def build_model(dim = 128, n_ch = 3, net_ind = 0, dropout = False, focal_loss = False): 
    inp = Input(shape = (dim, dim, n_ch), name = 'Image')
    # x = tf.cast(inp, tf.float32)
    # if net_ind < 8:
    #     x = tf.keras.applications.efficientnet.preprocess_input(x)
    # elif net_ind < 11:
    #     x = tf.keras.applications.efficientnet_v2.preprocess_input(x)
    # elif net_ind >= 11:
    #     x = tf.keras.applications.resnet_v2.preprocess_input(x)
    # else:
    #     print('Error - no such model!')
    #     return None
        
    # base = EFNS[net_ind](input_shape = (dim, dim, n_ch), weights='imagenet', include_top = False)
    base = EFNS[net_ind](input_shape = (dim, dim, n_ch), weights = None, include_top = False)
    x = base(inp)
    # x = base(x)
    x = GlobalAveragePooling2D()(x)
    if dropout:
        x = Dropout(0.1)(x)
    x = Dense(64, activation='relu')(x)
    if dropout:
        x = Dropout(0.3)(x)
    out = Dense(1, activation='sigmoid', name = 'Out')(x)
    
    model = tf.keras.Model(inputs = (inp), outputs = out)
    
    opt = tf.keras.optimizers.Adam(learning_rate=0.00005)
    pr_metric = PrecisionAtRecall(0.4, num_thresholds = 200, class_id=None, name = 'PatR', dtype=None)
    # pr_metric = PrecisionAtRecall(0.5, num_thresholds = 200, class_id=None, name = 'PatR', dtype=None)
    if focal_loss:
        model.compile(optimizer = opt, loss = Focal_Loss, metrics = ['AUC', ])
    else:
        loss = tf.keras.losses.BinaryCrossentropy(label_smoothing=0.05) 
        # model.compile(optimizer = opt, loss = loss, metrics = [pr_metric])
        # model.compile(optimizer = opt, loss = loss, metrics = [pr_metric, 'AUC'])
        model.compile(optimizer = opt, loss = loss, metrics = ['AUC'])
    # model.compile(optimizer=opt, loss=loss, metrics=['AUC'])
    # model.summary()
    return model

def build_model1(dim = 128, n_ch = 3, net_ind = 0, dropout = False, focal_loss = False): 
    inp = Input(shape = (dim, dim, n_ch), name = 'Image')
    x = tf.cast(inp, tf.float32)
    if net_ind < 8:
        x = tf.keras.applications.efficientnet.preprocess_input(x)
    elif net_ind < 11:
        x = tf.keras.applications.efficientnet_v2.preprocess_input(x)
    elif net_ind >= 11:
        x = tf.keras.applications.resnet_v2.preprocess_input(x)
    else:
        print('Error - no such model!')
        return None
        # x = tf.keras.applications.resnet_v2.preprocess_input(x)
        
    # base = EFNS[net_ind](input_shape = (dim, dim, n_ch), weights='imagenet', include_top = False)
    base = EFNS[net_ind](input_shape = (dim, dim, n_ch), weights=None, include_top = False)
    x = base(inp)
    x = GlobalAveragePooling2D()(x)
    if dropout:
        x = Dropout(0.1)(x)
    x = Dense(64, activation='relu')(x)
    if dropout:
        x = Dropout(0.3)(x)
    out = Dense(1, activation='sigmoid', name = 'Out')(x)
    
    model = tf.keras.Model(inputs = (inp), outputs = out)
    
    opt = tf.keras.optimizers.Adam(learning_rate=0.00005)
    if focal_loss:
        model.compile(optimizer = opt, loss = Focal_Loss, metrics = ['AUC'])
    else:
        loss = tf.keras.losses.BinaryCrossentropy(label_smoothing=0.05) 
        model.compile(optimizer = opt, loss = loss, metrics = ['AUC'])
    # model.compile(optimizer=opt, loss=loss, metrics=['AUC'])
    # model.summary()
    return model



# Below is TensorFlow code to perform coarse dropout data augmentation on tf.data.Dataset(). 
def dropout(image, DIM=256, PROBABILITY = 0.75, CT = 8, SZ = 0.2):
    # input image - is one image of size [dim,dim,3] not a batch of [b,dim,dim,3]
    # output - image with CT squares of side size SZ*DIM removed
    
    # DO DROPOUT WITH PROBABILITY DEFINED ABOVE
    P = tf.cast( tf.random.uniform([],0,1)<PROBABILITY, tf.int32)
    print(P)
    if (P==0)|(CT==0)|(SZ==0): print('rrr') 
    else: print('ffff')
    
    if (P==0)|(CT==0)|(SZ==0): return image
    
    for k in range(CT):
        # CHOOSE RANDOM LOCATION
        x = tf.cast( tf.random.uniform([],0,DIM),tf.int32)
        y = tf.cast( tf.random.uniform([],0,DIM),tf.int32)
        # COMPUTE SQUARE 
        WIDTH = tf.cast( SZ*DIM,tf.int32) * P
        ya = tf.math.maximum(0,y-WIDTH//2)
        yb = tf.math.minimum(DIM,y+WIDTH//2)
        xa = tf.math.maximum(0,x-WIDTH//2)
        xb = tf.math.minimum(DIM,x+WIDTH//2)
        # DROPOUT IMAGE
        one = image[ya:yb,0:xa,:]
        two = tf.zeros([yb-ya,xb-xa,3]) 
        three = image[ya:yb,xb:DIM,:]
        middle = tf.concat([one,two,three],axis=1)
        image = tf.concat([image[0:ya,:,:],middle,image[yb:DIM,:,:]],axis=0)
            
    # RESHAPE HACK SO TPU COMPILER KNOWS SHAPE OF OUTPUT TENSOR 
    image = tf.reshape(image,[DIM,DIM,3])
    return image


# Image Augmentation
sometimes = lambda aug: iaa.Sometimes(0.35, aug)
augmentation = iaa.Sequential([  
                                iaa.Fliplr(0.5),
                                iaa.Flipud(0.5),
                                # iaa.LinearContrast((0.9, 1.1)),
                                # iaa.Multiply((0.9, 1.1), per_channel=0.2),
                                sometimes(iaa.Cutout(nb_iterations=(1, 3), size=0.05, squared=False, fill_mode="constant", cval=0)),
                                sometimes(iaa.Crop(px=(20, 80), keep_size = True, sample_independently = False)),
                                sometimes(iaa.Affine(rotate=(-35, 35))),
                                sometimes(iaa.Affine(scale=(0.95, 1.05)))
                            ], random_order = True)       

@njit   
def BGR2MI(img):
    """
    Computes Melanin Index
    Parameters
    ----------
    img : array
        an image in BGR format 
    Returns
    -------
    integer arrays 
        MI, including normalised and rescaled
    """
    MI = 100 * np.log10(1/(img[:,:,2].astype('float')+1))
    MI_norm = (MI * 0.0042 + 1) * 255
    return MI_norm.astype('int16')


@njit
def BGR2EI(img):
    """
    Computes Erythema Index
    Parameters
    ----------
    img : array
        an image in BGR format 
    Returns
    -------
    integer arrays 
        EI, including normalised and rescaled
    """
    EI = 100 * (np.log10(1/(img[:,:,1].astype('float')+1)) - 1.44 * np.log10(1/(img[:,:,2].astype('float')+1)))
    EI_norm = (EI * 0.0017 + 0.4098) * 255
    return EI_norm.astype('int16')   


#---------------------------------------------------------------------------------------------
def read_img(path, desired_size, color_space = 'RGB', toAugment = False, drop_luminosity = False, sel_channels = '3'):
    """
    Will be used in DataGenerator
    Parameters
    ----------
    path : string
        path to the image.
    desired_size : tuple (x, y, ch)
        image size to which images shall be up/down-sized.
    color_space : string, optional
        what color space image shall be converted into. The default is 'RGB'.
    toAugment : boolean, optional
        if augmentation shall be applied to the image. The default is False.
    drop_luminosity : boolean, optional
        if Luminosity channel shall be omitted. The default is False.
    Returns
    -------
    img_exp : array
        image in the selected color space, could include extra channels for MI and EI.
    """
    with open(path, 'rb') as f:
        jf = f.read() # Read whole file in the file_content string
        if simplejpeg.is_jpeg(jf):
            img_BGR = simplejpeg.decode_jpeg(jf, colorspace = 'bgr')
    
    # to compensate for reduced number of channels passed in the image size        
    if drop_luminosity:
        n_ch = desired_size[2] + 1
    else:
        n_ch = desired_size[2]
    if img_BGR is None:
        main_logger.warning('Error load image:', path)
    
    if toAugment: 
        img_BGR = augmentation.augment_image(img_BGR)      
    
    if desired_size[0] != img_BGR.shape[0]:
        img_BGR = cv2.resize(img_BGR, desired_size[:2], interpolation=cv2.INTER_LINEAR)
        
    if color_space == 'HSV':
        img_exp = cv2.cvtColor(img_BGR, cv2.COLOR_BGR2HSV)
        if drop_luminosity:
            img_exp  = img_exp[:, :, :2]
    elif color_space == 'YCrCb': 
        img_exp = cv2.cvtColor(img_BGR, cv2.COLOR_BGR2YCrCb )
        if drop_luminosity:
            img_exp  = img_exp[:, :, 1:]
    else:           
        img_exp = img_BGR.copy()

    # changed the order of EI and MI in version 24, 
    # now EI will be used in 4 channels model instead of MI
    if n_ch == 4:
        if sel_channels == 'EI':
            EI_norm = BGR2EI(img_BGR)      
            EI_exp = np.expand_dims(EI_norm, axis = 2)
            img_exp = np.concatenate((img_exp, EI_exp), axis = 2)        
        else:
            MI_norm = BGR2MI(img_BGR)
            MI_exp = np.expand_dims(MI_norm, axis = 2)
            img_exp = np.concatenate((img_exp, MI_exp), axis = 2)        
    if n_ch == 5:
        if params['4TH_CHANNEL'] == 'EI':
        # if params['4TH_CHANNEL'] == 'EI':
            EI_norm = BGR2EI(img_BGR)      
            EI_exp = np.expand_dims(EI_norm, axis = 2)
            img_exp = np.concatenate((img_exp, EI_exp), axis = 2)        
        else:
            MI_norm = BGR2MI(img_BGR)
            MI_exp = np.expand_dims(MI_norm, axis = 2)
            img_exp = np.concatenate((img_exp, MI_exp), axis = 2)        
    # if n_ch > 4:
        # reverse which channel to add as 5th, since we've alreay added the 4th one
        if params['4TH_CHANNEL'] == 'EI':
            MI_norm = BGR2MI(img_BGR)
            MI_exp = np.expand_dims(MI_norm, axis = 2)
            img_exp = np.concatenate((img_exp, MI_exp), axis = 2)        
        else:
            EI_norm = BGR2EI(img_BGR)      
            EI_exp = np.expand_dims(EI_norm, axis = 2)
            img_exp = np.concatenate((img_exp, EI_exp), axis = 2)        

    return (img_exp / 255) # rescale to the range of [0, 1]
    # return img_exp   
                 
#---------------------------------------------------------------------------------------------
class DataGenerator(tf.keras.utils.Sequence):

    def __init__(self, list_IDs, labels = None, batch_size = 1, img_size = (512, 512, 1), 
                 img_dir = train_image_folder_path, color_space = 'RGB', testAugment = False, drop_luminosity = False,
                 sel_channels = '3',
                 *args, **kwargs):

        self.list_IDs = list_IDs
        self.labels = labels
        self.batch_size = batch_size
        self.img_size = img_size
        self.img_dir = img_dir
        self.testAugment = testAugment
        self.color_space = color_space
        self.drop_luminosity = drop_luminosity
        self.sel_channels = sel_channels
        self.on_epoch_end()

    def __len__(self):
        n_batches = int(math.ceil(len(self.indices) / self.batch_size))
        return n_batches

    def __getitem__(self, index):
        indices = self.indices[index*self.batch_size:(index+1)*self.batch_size]
        list_IDs_temp = [self.list_IDs[k] for k in indices]
        
        if self.labels is not None:
            X, Y = self.__data_generation(list_IDs_temp, indices)
            return X, Y
        else:
            X = self.__data_generation(list_IDs_temp)
            return X
        
    def on_epoch_end(self):
        
        if self.labels is not None: 
            self.indices = np.array(self.list_IDs.index)
        else:
            self.indices = np.array(self.list_IDs.index)

    def __data_generation(self, list_IDs_temp, idxs = None):
        X = np.empty((self.batch_size, *self.img_size))
         # print("Length : ", len(list_IDs_temp), ' : ', list_IDs_temp)
        
        if self.labels is not None: # training phase
            Y = np.empty((self.batch_size), dtype=np.float16)
        
            # ID is a filename
            for i, ID in enumerate(list_IDs_temp):
                X[i,] = read_img(self.img_dir+ID+".jpg", self.img_size, self.color_space, toAugment = True, 
                                 drop_luminosity = self.drop_luminosity, sel_channels = self.sel_channels)
                # X[i,] = _read(self.img_dir+ID+".jpg", self.img_size, self.color_space, toAugment = True, drop_luminosity = self.drop_luminosity)
                Y[i,] = self.labels.loc[idxs[i]]       
            return X, Y

        elif self.testAugment: # test phase with Augmentation
            for i, ID in enumerate(list_IDs_temp):
                X[i,] = read_img(self.img_dir+ID+".jpg", self.img_size, self.color_space, toAugment = True, 
                                 drop_luminosity = self.drop_luminosity, sel_channels = self.sel_channels)
                # X[i,] = _read(self.img_dir+ID+".jpg", self.img_size, self.color_space, toAugment = True, drop_luminosity = self.drop_luminosity)
            return X

        else: # test phase no Augmentation
            for i, ID in enumerate(list_IDs_temp):
                X[i,] = read_img(self.img_dir+ID+".jpg", self.img_size, self.color_space, toAugment = False, 
                                 drop_luminosity = self.drop_luminosity, sel_channels = self.sel_channels)
                # X[i,] = _read(self.img_dir+ID+".jpg", self.img_size, self.color_space, toAugment = False, drop_luminosity = self.drop_luminosity)
            return X


#---------------------------------------------------------------------------------------------
class TestSet():

    def __init__(self, list_IDs, labels = None, batch_size = 1, img_size = (512, 512, 1), channels = ['3', 'EI', 'MI', '5'],
                 img_dir = None, color_space = 'RGB', testAugment = False, drop_luminosity = False,
                 sel_channels = '3', n_folds = 5, name = '',
                 *args, **kwargs):

        # zero_l  = [np.zeros((len(list_IDs), n_folds))] * len(channels)
        # empty_l = [[]] * len(channels)
        # zero_dict  = dict(zip(channels.copy(), zero_l.copy()))
        # empty_dict = dict(zip(channels.copy(), empty_l.copy()))

        self.name = name
        self.list_IDs = list_IDs
        self.labels = labels
        self.batch_size = batch_size
        self.img_size = img_size
        self.img_dir = img_dir
        self.testAugment = testAugment
        self.color_space = color_space
        self.drop_luminosity = drop_luminosity
        self.sel_channels = sel_channels
        
        # self.roc_aucs =     empty_dict.copy()
        # self.pr_aucs =      empty_dict.copy()
        # self.f1s =          empty_dict.copy()
        # self.recalls =      empty_dict.copy()
        # self.precisions =   empty_dict.copy()
        # self.predictions =  copy.deepcopy(zero_dict)
        # # self.predictions =  zero_dict.copy()
        # self.roc_aucs_TTA =     empty_dict.copy()
        # self.pr_aucs_TTA =      empty_dict.copy()
        # self.f1s_TTA =          empty_dict.copy()
        # self.recalls_TTA =      empty_dict.copy()
        # self.precisions_TTA =   empty_dict.copy()
        # self.predictions_TTA =  copy.deepcopy(zero_dict)
        # # self.predictions_TTA =  zero_dict.copy()
        # self.roc_aucs_mean =    empty_dict.copy()
        # self.pr_aucs_mean =     empty_dict.copy()
        # self.precisions_mean =  empty_dict.copy()
        # self.recalls_mean =     empty_dict.copy()
        # self.f1s_mean =         empty_dict.copy()

        self.roc_aucs =     {'RGB' : [], '3':[], 'EI':[], 'MI':[], '5':[]}
        self.pr_aucs =      {'RGB' : [], '3':[], 'EI':[], 'MI':[], '5':[]}
        self.f1s =          {'RGB' : [], '3':[], 'EI':[], 'MI':[], '5':[]}
        self.recalls =      {'RGB' : [], '3':[], 'EI':[], 'MI':[], '5':[]}
        self.precisions =   {'RGB' : [], '3':[], 'EI':[], 'MI':[], '5':[]}
        self.predictions =  {'3': np.zeros((len(list_IDs), n_folds)), 
                              'EI': np.zeros((len(list_IDs), n_folds)), 
                              'MI': np.zeros((len(list_IDs), n_folds)), 
                              '5': np.zeros((len(list_IDs), n_folds)), 
                              'RGB': np.zeros((len(list_IDs), n_folds))}
        self.roc_aucs_TTA =     {'RGB' : [], '3':[], 'EI':[], 'MI':[], '5':[]}
        self.pr_aucs_TTA =      {'RGB' : [], '3':[], 'EI':[], 'MI':[], '5':[]}
        self.f1s_TTA =          {'RGB' : [], '3':[], 'EI':[], 'MI':[], '5':[]}
        self.recalls_TTA =      {'RGB' : [], '3':[], 'EI':[], 'MI':[], '5':[]}
        self.precisions_TTA =   {'RGB' : [], '3':[], 'EI':[], 'MI':[], '5':[]}
        self.predictions_TTA =  {'3': np.zeros((len(list_IDs), n_folds)), 
                                  'EI': np.zeros((len(list_IDs), n_folds)), 
                                  'MI': np.zeros((len(list_IDs), n_folds)), 
                                  '5': np.zeros((len(list_IDs), n_folds)), 
                                  'RGB': np.zeros((len(list_IDs), n_folds))}
        self.roc_aucs_mean =    {'RGB' : [], '3':[], 'EI':[], 'MI':[], '5':[]}
        self.pr_aucs_mean =     {'RGB' : [], '3':[], 'EI':[], 'MI':[], '5':[]}
        self.precisions_mean =  {'RGB' : [], '3':[], 'EI':[], 'MI':[], '5':[]}
        self.recalls_mean =     {'RGB' : [], '3':[], 'EI':[], 'MI':[], '5':[]}
        self.f1s_mean =         {'RGB' : [], '3':[], 'EI':[], 'MI':[], '5':[]}
        

    def __len__(self):
        return len(self.list_IDs)

    def get_test_gen(self, cur_img_size, cur_color_space, cur_channels):
        return DataGenerator(self.list_IDs, self.labels, self.batch_size, cur_img_size, 
                             self.img_dir, cur_color_space, self.testAugment, self.drop_luminosity, cur_channels)     
                 
    def get_last_metrics(self, cur_channel, cur_fold):
        roc_auc = roc_auc_score(self.labels, self.predictions[cur_channel][:, cur_fold])
        precision, recall, f1, _ = precision_recall_fscore_support(self.labels, self.predictions[cur_channel][:, cur_fold] >= 0.5, average = None)
        prec, rec, _ = precision_recall_curve(self.labels, self.predictions[cur_channel][:, cur_fold] )
        # prec, rec, _ = precision_recall_curve(self.labels, self.predictions[cur_channel][:, cur_fold] >= 0.5)
        auc_precision_recall = auc(rec, prec)
        # auc = roc_auc_score(self.labels, self.predictions[cur_channel][-1])
        # precision, recall, f1, _ = precision_recall_fscore_support(self.labels, self.predictions[cur_channel][-1] >= 0.5, average = None)
        self.roc_aucs[cur_channel].append(roc_auc)
        self.pr_aucs[cur_channel].append(auc_precision_recall)
        self.precisions[cur_channel].append(precision[1])
        self.recalls[cur_channel].append(recall[1])
        self.f1s[cur_channel].append(f1[1])
        pref = f'### Fold {cur_fold + 1}, {cur_channel} channels, -{self.name}-, without TTA, metrics'
        # pref = f'### Fold {cur_fold + 1}, {cur_channel} channels, {self.name}'
        print_log(f'{pref:<70}: ROC AUC = {roc_auc:.4f}, PR AUC = {auc_precision_recall:.4f}, F1 = {f1[1]:.4f}, precision = {precision[1]:.4f}, recall = {recall[1]:.4f}', [main_logger, res_logger])
        # print_log(f'{pref:<45} - metrics without TTA: ROC AUC = {roc_auc:.4f}, PR AUC = {auc_precision_recall:.4f}, F1 = {f1[1]:.4f}, precision = {precision[1]:.4f}, recall = {recall[1]:.4f}', [main_logger, res_logger])
        cm = confusion_matrix(self.labels, self.predictions[cur_channel][:, cur_fold] >= 0.5)
        print_log(f'Confusion matrix for {cur_channel} channel, fold {cur_fold + 1}', [main_logger])
        print_log(cm, [main_logger])

    def get_avg_metrics(self, cur_channel):
        preds = self.predictions[cur_channel].mean(axis=1)
        roc_auc = roc_auc_score(self.labels, preds)
        precision, recall, f1, _ = precision_recall_fscore_support(self.labels, preds >= 0.5, average = None)
        prec, rec, _ = precision_recall_curve(self.labels, preds)
        # prec, rec, _ = precision_recall_curve(self.labels, preds >= 0.5)
        auc_precision_recall = auc(rec, prec)

        self.roc_aucs_mean[cur_channel].append(roc_auc)
        self.pr_aucs_mean[cur_channel].append(auc_precision_recall)
        self.precisions_mean[cur_channel].append(precision[1])
        self.recalls_mean[cur_channel].append(recall[1])
        self.f1s_mean[cur_channel].append(f1[1])
        pref = f'### {cur_channel} channels, -{self.name}-, averaged across 5 folds, without TTA, metrics'
        print_log(f'{pref:<85}: ROC AUC = {roc_auc:.4f}, PR AUC = {auc_precision_recall:.4f}, F1 = {f1[1]:.4f}, precision = {precision[1]:.4f}, recall = {recall[1]:.4f}', [main_logger, res_logger])
        # pref = f'### {cur_channel} channels, {self.name}, averaged across 5 folds'
        # print_log(f'{pref:<45} - metrics without TTA: ROC AUC = {roc_auc:.4f}, PR AUC = {auc_precision_recall:.4f}, F1 = {f1[1]:.4f}, precision = {precision[1]:.4f}, recall = {recall[1]:.4f}', [main_logger, res_logger])

csv_logger = CSVLogger(model_logs + datetime.now().strftime("%Y%m%d-%H%M%S") + '-' + 'effnet_training_log.csv', separator = ',', append = True)

logdir = "logs_tb/scalars/" + datetime.now().strftime("%Y%m%d-%H%M%S")
file_writer = tf.summary.create_file_writer(logdir + "/metrics")
file_writer.set_as_default()
tensorboard_callback = TensorBoard(log_dir=logdir)

train_list_IDs = train_set.isic_id
test_list_IDs = df_test.isic_id
test_Kaggle_list_IDs = df_test_Kaggle.image_name
test_no_lesion_id_list_IDs = df_test_no_lesion_id.isic_id


VERBOSE = 1

skf = KFold(n_splits = n_folds, shuffle = True, random_state = SEED)
oof_preds = {}
oof_preds_TTA = {}

oof_preds_w = {}
oof_preds_w_TTA = {}

if params['COMPUTE_RGB']:
    channels = ['RGB', '3', 'EI', 'MI', '5']
    models   = {'RGB' : [], '3':[], 'EI':[], 'MI':[], '5':[]}
    weights  = {'RGB' : [], '3':[], 'EI':[], 'MI':[], '5':[]}
else:
    channels = ['3', 'EI', 'MI', '5']
    models   = {'3':[], 'EI':[], 'MI':[], '5':[]}
    weights  = {'3':[], 'EI':[], 'MI':[], '5':[]}

drop_luminosity_ch = params['DROP_LUM_CH']
cur_batch_size = params['BATCH_SIZES']
cur_img_size = (params['IMG_SIZES'], params['IMG_SIZES'], 3)
cur_color_space = params['COLOR_SPACE']

test_set_loc = TestSet(test_list_IDs, labels = y_test, batch_size = cur_batch_size, img_size = cur_img_size, channels = channels,
                         img_dir = test_image_folder_path, color_space = cur_color_space, testAugment = False, 
                         drop_luminosity = drop_luminosity_ch, name = 'Local Test')                      
test_set_Kaggle = TestSet(test_Kaggle_list_IDs, labels = None, batch_size = cur_batch_size, img_size = cur_img_size, channels = channels,
                         img_dir = test_Kaggle_image_folder_path, color_space = cur_color_space, testAugment = False, 
                         drop_luminosity = drop_luminosity_ch, name = 'Kaggle Test')                      
test_set_NoL = TestSet(test_no_lesion_id_list_IDs, labels = y_test_no_lesion, batch_size = cur_batch_size, img_size = cur_img_size, channels = channels,
                         img_dir = test_no_lesion_id_image_folder_path, color_space = cur_color_space, testAugment = False, 
                         drop_luminosity = drop_luminosity_ch, name = 'No Lesion Id Test')                      


for fold, (idxT, idxV) in enumerate(skf.split(train_IP_set)):

    print_log('-' * 80, [main_logger, res_logger])
    print_log(f'Fold #: {fold+1}, Model: {EFNS[params["EFF_NETS"]].__name__}, BS: {params["BATCH_SIZES"]}, Image Size: {params["IMG_SIZES"]}', [main_logger, res_logger])
    train_IPs = train_IP_set[idxT]
    val_IPs = train_IP_set[idxV]
    train_image_names = train_set.loc[train_set.patient_id.isin(train_IPs), 'isic_id']
    val_image_names = train_set.loc[train_set.patient_id.isin(val_IPs), 'isic_id']
    train_I = train_image_names.index.to_numpy()
    val_I = val_image_names.index.to_numpy()

    y_train_set = train_set.loc[train_set.patient_id.isin(train_IPs), 'target']
    y_val_set = train_set.loc[train_set.patient_id.isin(val_IPs), 'target']
        
    for n_ch, ch in enumerate(channels): # running the same model with inputs of just RGB, RGB+EI, RGB+MI, RGB+MI+EI for each fold
        print_log('-'*25, [main_logger])
        cur_color_space = params['COLOR_SPACE']
        
        if n_ch == 4:
        # if n_ch == 3:
            n_channels = 5
        elif n_ch == 0:
            n_channels = 3
            cur_color_space  = 'RGB'
        elif n_ch == 1:
            n_channels = 3
        else:
            n_channels = 4
            
        if (cur_color_space != 'RGB') & (drop_luminosity_ch):
            cur_num_channels = n_channels - 1
        else:
            cur_num_channels = n_channels
            
        print_log(f'Number of channels: {cur_num_channels} using {ch}', [main_logger])

        # with strategy.scope():
        with tf.device('/GPU:0'):
        # with tf.device('/GPU:1'):
            
            models[ch] = build_model(dim = params['IMG_SIZES'], n_ch = cur_num_channels, net_ind = params['EFF_NETS'], dropout = False, focal_loss = params['FOCAL_LOSS'])
            cur_img_size = (params['IMG_SIZES'], params['IMG_SIZES'], cur_num_channels)
            print_log(f'Image Size: {cur_img_size}', [main_logger])
        
            idxT_ext = shuffle(train_I, random_state = SEED)
            x_trn_ext = train_image_names.loc[idxT_ext].reset_index(drop = True)
            y_trn_ext = y_train_set.loc[idxT_ext].reset_index(drop = True)
            
            trn_gen = DataGenerator(x_trn_ext, labels = y_trn_ext, batch_size = cur_batch_size, img_size = cur_img_size, 
                                    img_dir = train_image_folder_path, color_space = cur_color_space, testAugment = False, 
                                    drop_luminosity = drop_luminosity_ch, sel_channels = ch)
            val_gen = DataGenerator(val_image_names, labels = y_val_set, batch_size = cur_batch_size, img_size = cur_img_size, 
                                    img_dir = train_image_folder_path, color_space = cur_color_space, testAugment = False, 
                                    drop_luminosity = drop_luminosity_ch, sel_channels = ch)
        
            # SAVE BEST MODEL EACH FOLD
            sv = ModelCheckpoint(
                f'{EFNS[params["EFF_NETS"]].__name__}_fold_{fold}-{ch}.h5', monitor='val_loss', verbose=1, save_best_only=True,
                # f'fold_{fold}-{ch}.h5', monitor='val_loss', verbose=1, save_best_only=True,
                # f'fold_{fold}-{cur_num_channels}.h5', monitor='val_loss', verbose=1, save_best_only=True,
                save_weights_only=True, mode='min', save_freq='epoch')    
        
            history = models[ch].fit(
                trn_gen, 
                epochs = params['EPOCHS'], 
                # callbacks = [sv, tensorboard_callback, get_lr_callback(cur_batch_size)], 
                # callbacks = [sv, csv_logger, tensorboard_callback, get_lr_callback(cur_batch_size)], 
                callbacks = [sv, csv_logger, tensorboard_callback, get_lr_callback_kaggle(cur_batch_size)], 
                validation_data = val_gen,
                verbose = VERBOSE
            )
            print_log(f'Loading best model for fold {fold+1} with {cur_num_channels} channels using {ch}', [main_logger])
            models[ch].load_weights(f'{EFNS[params["EFF_NETS"]].__name__}_fold_{fold}-{ch}.h5') 
            # models[ch].load_weights(f'fold_{fold}-{ch}.h5') 
                
            n_TTA = params["TTA"]
            test_gen =          test_set_loc.get_test_gen(cur_img_size, cur_color_space, ch)
            test_gen_Kaggle =   test_set_Kaggle.get_test_gen(cur_img_size, cur_color_space, ch)
            test_gen_NoL =      test_set_NoL.get_test_gen(cur_img_size, cur_color_space, ch)

            print_log('Predicting Local Test without TTA...', [main_logger])
            pred = models[ch].predict(test_gen, verbose = 1)[:len(test_list_IDs)]  
            test_set_loc.predictions[ch][:, fold] += pred[:,0] 

            print_log('Predicting Kaggle Test without TTA...', [main_logger])
            pred = models[ch].predict(test_gen_Kaggle, verbose = 1)[:len(test_Kaggle_list_IDs)]  
            test_set_Kaggle.predictions[ch][:, fold] += pred[:,0] 

            print_log('Predicting No Lesions Id Test without TTA...', [main_logger])
            pred = models[ch].predict(test_gen_NoL, verbose = 1)[:len(test_no_lesion_id_list_IDs)]  
            test_set_NoL.predictions[ch][:, fold] += pred[:,0] 


            # PREDICT TEST USING TTA
            if n_TTA > 0:
                print_log(f'Predicting Test with {n_TTA} TTA...', [main_logger])
                # test_gen = DataGenerator(test_list_IDs, labels = None, batch_size = cur_batch_size, img_size = cur_img_size, 
                #                          img_dir = test_image_folder_path, color_space = cur_color_space, testAugment = True, 
                #                          drop_luminosity = drop_luminosity_ch, sel_channels = ch)                      
                # test_gen_Kaggle = DataGenerator(test_Kaggle_list_IDs, labels = None, batch_size = cur_batch_size, img_size = cur_img_size, 
                #                          img_dir = test_image_folder_path, color_space = cur_color_space, testAugment = True, 
                #                          drop_luminosity = drop_luminosity_ch, sel_channels = ch)                      
                # test_gen_NoL = DataGenerator(test_no_lesion_id_list_IDs, labels = None, batch_size = cur_batch_size, img_size = cur_img_size, 
                #                          img_dir = test_image_folder_path, color_space = cur_color_space, testAugment = True, 
                #                          drop_luminosity = drop_luminosity_ch, sel_channels = ch)                      
                # pred_TTA = models[ch].predict(test_gen, verbose = 1)[:len(test_list_IDs)]  
                # for n in tqdm(range(n_TTA - 1)):
                #     pred_TTA += models[ch].predict(test_gen, verbose = 0)[:len(test_list_IDs)]  
                # preds_TTA[ch][:, fold] = pred_TTA[:, 0] / n_TTA
        

            
            # REPORT RESULTS
            test_set_loc.get_last_metrics(ch, fold)
            test_set_NoL.get_last_metrics(ch, fold)
            # print_log('\n', [main_logger, res_logger])


            # auc = roc_auc_score(y_test_set, val_pr)
            # precision, recall, f1, _ = precision_recall_fscore_support(y_test_set, val_pr >= 0.5, average = None)
            # oof_aucs[ch].append(auc)
            # print_log(f'#### Fold {fold+1}, {cur_num_channels}channels OOF AUC without TTA = {auc:.4f}, F1 = {f1[1]:.4f}, precision = {precision[1]:.4f}, recall = {recall[1]:.4f}', [main_logger, res_logger])

            # if n_TTA > 0:
            #     auc = roc_auc_score(y_test_set, val_pr_TTA / n_TTA)
            #     oof_aucs_TTA[ch].append(auc)
            #     precision, recall, f1, _ = precision_recall_fscore_support(y_test_set, (val_pr_TTA / n_TTA) >= 0.5, average = None)
            #     print_log(f'#### Fold {fold+1}, {cur_num_channels}channels OOF AUC with {n_TTA} TTA = {auc:.4f}, F1 = {f1[1]:.4f}, precision = {precision[1]:.4f}, recall = {recall[1]:.4f}', [main_logger, res_logger])

MM_scaler = MinMaxScaler()

print_log('\n'+'-'*80, [main_logger, res_logger])
for n_ch, ch in enumerate(channels): # running the same model with inputs of just RGB, RGB+EI, RGB+MI, RGB+MI+EI for each fold
    test_set_loc.get_avg_metrics(ch)
    cm = confusion_matrix(test_set_loc.labels, test_set_loc.predictions[ch].mean(axis=1) >= 0.5)
    print_log(f'Confusion matrix for {ch}', [main_logger])
    print_log(cm, [main_logger])
    
    test_set_NoL.get_avg_metrics(ch)
    cm = confusion_matrix(test_set_NoL.labels, test_set_NoL.predictions[ch].mean(axis=1) >= 0.5)
    print_log(f'Confusion matrix for {ch}', [main_logger])
    print_log(cm, [main_logger])

    # # get average predicted target between folds for the selected number of channels
    # oof_preds[ch] = test_set_loc.predictions[ch].mean(axis=0)
    # # oof_preds[ch] = np.array(oof_pred[ch]).mean(axis=0)
    # roc_auc = roc_auc_score(test_set_loc.labels, oof_preds[ch])
    # # auc = roc_auc_score(y_test_set, oof_preds[ch])
    # precision, recall, f1, _ = precision_recall_fscore_support(test_set_loc.labels, oof_preds[ch] >= 0.5, average = None)
    # # precision, recall, f1, _ = precision_recall_fscore_support(y_test_set, oof_preds[ch] >= 0.5, average = None)
    # print_log(f'\nOverall OOF AUC {ch} channels without TTA = {auc:.4f}, F1 = {f1[1]:.4f}, precision = {precision[1]:.4f}, recall = {recall[1]:.4f}', [main_logger, res_logger])
    
    # if n_TTA > 0:
    #     oof_preds_TTA[ch] = np.array(oof_pred_TTA[ch]).mean(axis=0)
    #     auc = roc_auc_score(y_test_set, oof_preds_TTA[ch])
    #     precision, recall, f1, _ = precision_recall_fscore_support(y_test_set, oof_preds_TTA[ch] >= 0.5, average = None)
    #     print_log(f'\nOverall OOF AUC {ch} channels with {n_TTA} TTA = {auc:.4f}, F1 = {f1[1]:.4f}, precision = {precision[1]:.4f}, recall = {recall[1]:.4f}', [main_logger, res_logger])
    
    # compute weight based on AUC on validation set for each fold 
    # will use to give more weight to better folds for predicted target 
    scaler = (np.array(test_set_loc.roc_aucs[ch]).max() - np.array(test_set_loc.roc_aucs[ch]).min()+1) 
    weights[ch]= (test_set_loc.roc_aucs[ch] - np.array(test_set_loc.roc_aucs[ch]).min()/2) / scaler
    # scaler = (np.array(oof_aucs[ch]).max() - np.array(oof_aucs[ch]).min()+1) 
    # weights[ch]= (np.array(oof_aucs[ch]) - np.array(oof_aucs[ch]).min()/2)/ scaler
    
    # weighted average between folds/models
    oof_preds_w[ch] = np.squeeze(test_set_loc.predictions[ch]).dot(weights[ch])
    # oof_preds_w[ch] = np.squeeze(test_set_loc.predictions[ch]).T.dot(weights[ch])
    op = MM_scaler.fit_transform(oof_preds_w[ch].reshape(-1, 1))
    # oof_preds_w[ch] = np.squeeze(np.array(oof_pred[ch])).T.dot(weights[ch])
    # op = MM_scaler.fit_transform(oof_preds_w[ch].reshape(-1, 1))
    auc_w = roc_auc_score(test_set_loc.labels, op)
    # auc_w = roc_auc_score(y_test_set, oof_preds_w[ch])
    pr_Score , recall, f1, _ = precision_recall_fscore_support(test_set_loc.labels, op >= 0.5, average = None)
    # prec, rec, thr = precision_recall_curve(test_set_loc.labels, op >= 0.5)
    prec, rec, thr = precision_recall_curve(test_set_loc.labels, op)
    auc_precision_recall = auc(rec, prec)
    AP_score = average_precision_score(test_set_loc.labels, op)
    # pr_Score , recall, f1, _ = precision_recall_fscore_support(y_test_set, op >= 0.5, average = None)
    # print_log(f'Mean weighted over 5 folds ROC AUC for {ch} channels over local test set, no TTA = {auc_w:.4f}', [main_logger, res_logger])
    # print_log(f'Threshold 0.5 weighted: f1 = {f1[1]:0.2f}, precision = {pr_Score[1]:0.2f}, recall = {recall[1]:0.2f}', [main_logger, res_logger])
    ts = f'    Mean weighted over 5 folds for {ch} channels over local test set, no TTA'
    print_log(f'{ts:<85} - ROC AUC = {auc_w:.4f}, PR ROC = {auc_precision_recall:.4f}, f1 = {f1[1]:0.4f}, precision = {pr_Score[1]:0.4f}, recall = {recall[1]:0.4f}, Average precision score = {AP_score:0.4f}', [main_logger, res_logger])
    cm = confusion_matrix(test_set_loc.labels, op >= 0.5)
    print_log(f'Confusion matrix for {ch}, mean weighted', [main_logger])
    print_log(cm, [main_logger])
    
    scaler = (np.array(test_set_NoL.roc_aucs[ch]).max() - np.array(test_set_NoL.roc_aucs[ch]).min()+1) 
    weights[ch]= (test_set_NoL.roc_aucs[ch] - np.array(test_set_NoL.roc_aucs[ch]).min()/2) / scaler  
    # weighted average between folds/models
    oof_preds_w[ch] = np.squeeze(test_set_NoL.predictions[ch]).dot(weights[ch])
    op = MM_scaler.fit_transform(oof_preds_w[ch].reshape(-1, 1))
    auc_w = roc_auc_score(test_set_NoL.labels, op)
    pr_Score , recall, f1, _ = precision_recall_fscore_support(test_set_NoL.labels, op >= 0.5, average = None)
    prec, rec, thr = precision_recall_curve(test_set_NoL.labels, op)
    auc_precision_recall = auc(rec, prec)
    AP_score = average_precision_score(test_set_NoL.labels, op)
    ts = f'    Mean weighted over 5 folds for {ch} channels over NoL test set, no TTA'
    print_log(f'{ts:<85} - ROC AUC = {auc_w:.4f}, PR ROC = {auc_precision_recall:.4f}, f1 = {f1[1]:0.4f}, precision = {pr_Score[1]:0.4f}, recall = {recall[1]:0.4f}, Average precision score = {AP_score:0.4f}', [main_logger, res_logger])
    cm = confusion_matrix(test_set_NoL.labels, op >= 0.5)
    print_log(f'Confusion matrix for {ch}, mean weighted', [main_logger])
    print_log(cm, [main_logger])

    print_log('\n', [main_logger, res_logger])
    
    target = test_set_Kaggle.predictions[ch].dot(weights[ch].T)
    # target = preds[ch].dot(weights[ch].T)
    target_scaled = MM_scaler.fit_transform(target.reshape(-1, 1))
    submission = pd.DataFrame(dict(image_name = df_test_Kaggle.image_name, target = target_scaled[:, 0]))
    submission = submission.sort_values('image_name') 
    submission.to_csv(f"{n_folds}_{nets_names[params['EFF_NETS']]}_{params['IMG_SIZES']}_{ch}ch_w_{params['MAL_UPSAMPLE']}ups_{params['COLOR_SPACE']}_CV{'0'+str(auc_w)[2:6]}-ISIC.csv", index=False)
    
    # if n_TTA > 0:
    #     oof_preds_w_TTA[ch] = np.squeeze(np.array(oof_pred_TTA[ch])).T.dot(weights[ch])
    #     op = MM_scaler.fit_transform(oof_preds_w_TTA[ch].reshape(-1, 1))
    #     auc_w = roc_auc_score(y_test_set, op)
    #     pr_Score , recall, f1, _ = precision_recall_fscore_support(y_test_set, op >= 0.5, average = None)
    #     # auc_w = roc_auc_score(y_test_set, oof_preds_w_TTA[ch])
    #     print_log(f'Overall OOF AUC weighted with {ch} channels with {n_TTA} TTA = {auc_w:.4f}', [main_logger, res_logger])
    #     print_log(f'Threshold 0.5 weighted with {n_TTA} TTA: f1 = {f1[1]:0.2f}, precision = {pr_Score[1]:0.2f}, recall = {recall[1]:0.2f}', [main_logger, res_logger])
        
    #     target_TTA = preds_TTA[ch].dot(weights[ch].T)
    #     target_scaled = MM_scaler.fit_transform(target_TTA.reshape(-1, 1))
    #     submission = pd.DataFrame(dict(image_name = df_test.isic_id, target = target_scaled[:, 0]))
    #     # submission = pd.DataFrame(dict(image_name = df_test.image_name, target = target_scaled[:, 0]))
    #     submission = submission.sort_values('image_name') 
    #     submission.to_csv(f"{n_folds}_{nets_names[params['EFF_NETS'][0]]}_{params['IMG_SIZES'][0]}_{ch}ch_w_{n_TTA}TTA_{params['MAL_UPSAMPLE']}ups_{params['COLOR_SPACE']}_CV{'0'+str(auc_w)[2:6]}.csv", index=False)
    

print_log(f'\nParameters:\n{params}', [main_logger, res_logger])
save_name = f"{n_folds}_{nets_names[params['EFF_NETS']]}_{params['IMG_SIZES']}_{ch}ch_w_{n_TTA}TTA_{params['MAL_UPSAMPLE']}ups_{params['COLOR_SPACE']}_CV{'0'+str(auc_w)[2:6]}"
with open(f"{save_name}.params", 'wb') as f: 
# with open(f"{n_folds}_{nets_names[params['EFF_NETS'][0]]}_{params['IMG_SIZES'][0]}_{ch}ch_w_{n_TTA}TTA_{params['MAL_UPSAMPLE']}ups_{params['COLOR_SPACE']}_CV{'0'+str(auc_w)[2:6]}.params", 'wb') as f: 
    pickle.dump(params, f)               

# save_name = f"{n_folds}_{nets_names[params['EFF_NETS']]}_{params['IMG_SIZES']}_{ch}ch_w_{n_TTA}TTA_{params['MAL_UPSAMPLE']}ups_{params['COLOR_SPACE']}_CV{'0'+str(auc_w)[2:6]}"
# save_name = f"{n_folds}_{nets_names[params['EFF_NETS']]}_{params['IMG_SIZES']}_{ch}ch_w_{n_TTA}TTA_{params['MAL_UPSAMPLE']}ups_{params['COLOR_SPACE']}_CV{'00000'}"
with open(f"{save_name}_test_loc.testobj", 'wb') as f: 
    pickle.dump(test_set_loc, f)               
with open(f"{save_name}_test_NoL.testobj", 'wb') as f: 
    pickle.dump(test_set_NoL, f)               
    

plot_mean_ROC(test_set_loc.labels, test_set_loc.predictions, channels, model_descr = f'{nets_names[params["EFF_NETS"]]}-full-ISIC', to_dir = f'{model_logs}/{save_name}_ROC_PR_plots', channels_first=False)
plot_mean_PR(test_set_loc.labels, test_set_loc.predictions, channels, model_descr = f'{nets_names[params["EFF_NETS"]]}-full-ISIC', to_dir = f'{model_logs}/{save_name}_ROC_PR_plots', channels_first=False)

df_mean_metrics_temp_loc = pd.DataFrame(columns = mean_metrics_cols, index = channels)
df_mean_metrics_temp_NoL = pd.DataFrame(columns = mean_metrics_cols, index = channels)

for n_ch, ch in enumerate(channels):
    df_mean_metrics_temp_loc.loc[ch] = [datetime_now, nets_names[params["EFF_NETS"]], params["IMG_SIZES"], params["BATCH_SIZES"], 
                                        ch, 'test_loc',
                                        test_set_loc.roc_aucs_mean[ch][0], test_set_loc.pr_aucs_mean[ch][0], test_set_loc.f1s_mean[ch][0], 
                                        test_set_loc.precisions_mean[ch][0], test_set_loc.recalls_mean[ch][0]]
    df_mean_metrics_temp_NoL.loc[ch] = [datetime_now, nets_names[params["EFF_NETS"]], params["IMG_SIZES"], params["BATCH_SIZES"], 
                                        ch, 'test_NoL',
                                        test_set_NoL.roc_aucs_mean[ch][0], test_set_NoL.pr_aucs_mean[ch][0], test_set_NoL.f1s_mean[ch][0], 
                                        test_set_NoL.precisions_mean[ch][0], test_set_NoL.recalls_mean[ch][0]]

df_mean_metrics = pd.concat([df_mean_metrics, df_mean_metrics_temp_NoL, df_mean_metrics_temp_loc]).reset_index(drop = True)    
    
# with open(".\\models_ISIC\\5_v1b0_256_5ch_w_5ups_HSV_CV08716-ISIC\\5_v1b0_256_5ch_w_0TTA_5ups_HSV_CV08716_test_loc.testobj", 'rb') as f: 
#     test_set_loc = pickle.load(f)               

# with open(".\\models_ISIC\\5_v1b0_256_5ch_w_5ups_HSV_CV08716-ISIC\\5_v1b0_256_5ch_w_0TTA_5ups_HSV_CV08716_test_NoL.testobj", 'rb') as f: 
#     test_set_NoL = pickle.load(f)               

# df_fold_metrics.to_csv(f'{data_path}/fold_metrics.csv', index = False)
df_mean_metrics.to_csv(f'{data_path}/mean_metrics.csv', index = False)


close_loggers(loggers)


# test_set_loc.predictions[ch] = 125
# test_set_loc.predictions[ch] += test_set_loc.predictions['3']
# test_set_loc.predictions[ch][:, 1] += pred[:,0] 

# test_set_NoL.predictions['5'][:, 2] += pred[:,0] 

# id(test_set_NoL.predictions['3'])
# id(test_set_NoL.predictions['5'])

# id(test_set_NoL.predictions_TTA['3'])
# id(test_set_NoL.predictions['5'])

# id(test_set_NoL.roc_aucs['5'])
# id(test_set_NoL.roc_aucs['3'])
