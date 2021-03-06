import torch
import torchvision
from torch.autograd import Variable
import torch.nn as nn
import os
import torch.nn.functional as F
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

from torch.utils.data import Dataset, DataLoader
from torchvision import transforms, utils
import torch.optim as optim
import torchvision.transforms as standard_transforms

import numpy as np
import glob

from data_loader import Rescale
from data_loader import RescaleT
from data_loader import RandomCrop
from data_loader import ToTensor
from data_loader import ToTensorLab
from data_loader import SalObjDataset

from model import STEB_UNet

import matplotlib
matplotlib.use('AGG')
import matplotlib.pyplot as plt

import eval
from collections import OrderedDict
import dice_loss
import time

# ------- 1. define loss function --------

bce_loss = nn.BCELoss(size_average=True)

# ------- 2. set the directory of training dataset --------

model_name = 'TransUNet_dice' 

train_data = '../The cropped image tiles and raster labels/train_all/'
tra_image_dir = os.path.join('image' + os.sep)
tra_label_dir = os.path.join('label' + os.sep)

image_ext = '.png'
label_ext = '.png'

model_dir = os.path.join(os.getcwd(), 'saved_models/WSU-dataset/', model_name + os.sep)

epoch_num = 300
batch_size_train = 1
batch_size_val = 1
train_num = 0
val_num = 0

ite_num = 0
running_loss = 0.0
running_tar_loss = 0.0
ite_num4val = 0
save_epoch = 5
Loss_list = []

tra_img_name_list = glob.glob(train_data + tra_image_dir + '*' + image_ext)

tra_lbl_name_list = []

for img_path in tra_img_name_list:
	img_name = img_path.split(os.sep)[-1]

	aaa = img_name.split(".")
	bbb = aaa[0:-1]
	imidx = bbb[0]
	for i in range(1,len(bbb)):
		imidx = imidx + "." + bbb[i]

	tra_lbl_name_list.append(train_data + tra_label_dir + imidx + label_ext)

print("---")
print("train images: ", len(tra_img_name_list))
print("train labels: ", len(tra_lbl_name_list))
print("---")

train_num = len(tra_img_name_list)

train_dataset = SalObjDataset(
    img_name_list=tra_img_name_list,
    lbl_name_list=tra_lbl_name_list,
    transform=transforms.Compose([
        RescaleT(160),
        RandomCrop(128),
        ToTensorLab(flag=0)]))
train_dataloader = DataLoader(train_dataset, batch_size=batch_size_train, shuffle=True, num_workers=1)

# ------- 3. define model --------
# define the net
net = STEB_UNet(in_channels=3, out_channels = 1)
net = nn.DataParallel(net) # multi-GPU

if torch.cuda.is_available():
    net.cuda()

# ------- 4. define optimizer --------
print("---define optimizer...")
optimizer = optim.Adam(net.parameters(), lr=0.001, betas=(0.9, 0.999), eps=1e-08, weight_decay=0)

# ------- loading the latest model -------
if not os.path.exists(model_dir):
    os.makedirs(model_dir)
model_list = os.listdir(model_dir)
e_from = 0

if len(model_list) != 0: #load the latest model
    model_list.sort(key=lambda x:os.path.getmtime(os.path.join(model_dir,x)))
    latest_file = model_list[-1]
    print("Previous training is interrupted. Begin training from {}.".format(latest_file))
    state_dict = torch.load(os.path.join(model_dir,latest_file))
    net.load_state_dict(state_dict['state_dict'])
    optimizer.load_state_dict(state_dict['optimizer'])
    e_from = state_dict['epoch'] + 1

# ------- 5. training process --------
print("---start training...")

for epoch in range(e_from, epoch_num):
    since = time.time()
    net.train()

    for i, data in enumerate(train_dataloader):
        ite_num = ite_num + 1
        ite_num4val = ite_num4val + 1

        inputs, labels = data['image'], data['label']

        inputs = inputs.type(torch.FloatTensor)
        labels = labels.type(torch.FloatTensor)

        # wrap them in Variable
        if torch.cuda.is_available():
            inputs_v, labels_v = Variable(inputs.cuda(), requires_grad=False), Variable(labels.cuda(),
                                                                                        requires_grad=False)
        else:
            inputs_v, labels_v = Variable(inputs, requires_grad=False), Variable(labels, requires_grad=False)

        # y zero the parameter gradients
        optimizer.zero_grad()

        # forward + backward + optimize
        d= net(inputs_v)
        loss = bce_loss(d, labels_v)
        #loss = dice_loss.dice_coeff(d, labels_v)
        loss.backward()
        optimizer.step()

        # # print statistics
        running_loss += loss.data

        # del temporary outputs and loss
        del d, loss

        print("[epoch: %3d/%3d, batch: %5d/%5d, ite: %d] train loss: %3f" % (
        epoch + 1, epoch_num, (i + 1) * batch_size_train, train_num, ite_num, running_loss / ite_num4val))

    time_elapsed = time.time() - since
    print('Training complete in {}s'.format(time_elapsed))

    if (epoch+1) % save_epoch== 0:
        torch.save({'epoch': epoch + 1, 'state_dict': net.state_dict(), 'optimizer': optimizer.state_dict()}, 
                    model_dir + model_name+"_bce_itr_%d_train_%3f.pth" % (epoch+1, running_loss / ite_num4val))
        

    Loss_list.append(running_loss / ite_num4val)
    running_loss = 0.0
    running_tar_loss = 0.0
    net.train()  # resume train
    ite_num4val = 0
        
    # x = range(0, len(Loss_list))
    # y = Loss_list
    # plt.plot(x, y, '.-')
    # plt.xlabel('Test loss vs. ite_num')
    # plt.ylabel('Test loss')
    # plt.savefig("loss/WHU_TransUNet_dice.png".format(str(epoch+1)))
