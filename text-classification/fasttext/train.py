# 
# Copyright (c) 2017-2019 Minato Sato
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.
#

"""
This is implementation of fasttext with bigram features.
see [Bag of Tricks for Efficient Text Classification](https://arxiv.org/abs/1607.01759)
"""

import sys
sys.path.append('../../')

import numpy as np

import nnabla as nn
import nnabla.functions as F
import nnabla.parametric_functions as PF
import nnabla.solvers as S

from nnabla.utils.data_iterator import data_iterator_simple

from pathlib import Path
from tqdm import tqdm

from common.functions import time_distributed
from common.functions import get_mask
from common.utils import load_imdb
from common.utils import with_padding

from common.trainer import Trainer

import argparse
parser = argparse.ArgumentParser(description='Encoder-decoder model training.')
parser.add_argument('--context', '-c', type=str,
                    default='cpu', help='You can choose cpu or cudnn.')
parser.add_argument('--device', '-d', type=int,
                    default=0, help='You can choose the device id when you use cudnn.')
args = parser.parse_args()

if args.context == 'cudnn':
    from nnabla.ext_utils import get_extension_context
    ctx = get_extension_context('cudnn', device_id=args.device)
    nn.set_default_context(ctx)

max_len: int = 400
batch_size: int = 32
embedding_size: int = 50
max_epoch: int = 5
vocab_size: int = 20000

x_train, x_test, y_train, y_test = load_imdb(vocab_size)

def get_bigram(sentence):
    return list(zip(sentence[:len(sentence)-1], sentence[1:]))

bigram_dict: dict = dict()
bigram_index = vocab_size

print("making bigram dictionary...")
for sentence in tqdm(x_train):
    for bigram in set(get_bigram(sentence)):
        if bigram not in bigram_dict:
            bigram_dict[bigram] = bigram_index
            bigram_index += 1

vocab_size = bigram_index + 1
    
print("adding bigram to dataset..")
for i, sentence in enumerate(tqdm(x_train)):
    for bigram in get_bigram(sentence):
        if bigram in bigram_dict:
            x_train[i].append(bigram_dict[bigram])
for i, sentence in enumerate(tqdm(x_test)):
    for bigram in get_bigram(sentence):
        if bigram in bigram_dict:
            x_test[i].append(bigram_dict[bigram])

x_train = with_padding(x_train, padding_type='post', max_sequence_length=max_len)
x_test = with_padding(x_test, padding_type='post', max_sequence_length=max_len)
y_train = y_train[:, None]
y_test = y_test[:, None]

num_train_batch = len(x_train)//batch_size
num_dev_batch = len(x_test)//batch_size

def load_train_func(index):
    return x_train[index], y_train[index]

def load_dev_func(index):
    return x_test[index], y_test[index]

train_data_iter = data_iterator_simple(load_train_func, len(x_train), batch_size, shuffle=True, with_file_cache=False)
dev_data_iter = data_iterator_simple(load_dev_func, len(x_test), batch_size, shuffle=True, with_file_cache=False)

def global_average_pooling_1d(x, mask):
    count = F.sum(mask, axis=1)
    global_average_pooled = F.sum(h, axis=1) / count
    return global_average_pooled

x = nn.Variable((batch_size, max_len))
t = nn.Variable((batch_size, 1))
mask = get_mask(x)
with nn.parameter_scope('embedding'):
    h = time_distributed(PF.embed)(x, vocab_size, embedding_size) * mask
h = global_average_pooling_1d(h, mask)
with nn.parameter_scope('output'):
    y = F.sigmoid(PF.affine(h, 1))

accuracy = F.mean(F.equal(F.round(y), t))
loss = F.mean(F.binary_cross_entropy(y, t))

# Create solver.
solver = S.Adam()
solver.set_parameters(nn.get_parameters())

trainer = Trainer(inputs=[x, t], loss=loss, metrics={'cross entropy': loss, 'accuracy': accuracy}, solver=solver)
trainer.run(train_data_iter, dev_data_iter, epochs=5, verbose=1)


