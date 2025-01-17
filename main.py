import sys
import os
import os.path
import glob
import logging
import argparse
import numpy as np
import torch
from load_data import DATA
from run import train, test
from utils import try_makedirs, load_model, get_file_name_identifier
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

def train_one_dataset(params, file_name, train_data, valid_data):
    # ================================== model initialization ==================================

    model = load_model(params)
    optimizer = torch.optim.Adam(
        model.parameters(), lr=params.lr, betas=(0.9, 0.999), eps=1e-8)
    print("\n")

    # ================================== start training ==================================
    all_train_loss = {}
    all_train_acc = {}
    all_train_auc = {}
    all_valid_loss = {}
    all_valid_acc = {}
    all_valid_auc = {}
    best_valid_auc = 0

    for idx in range(params.max_iter):
        # Train Model
        train_loss, train_acc, train_auc = train(
            model, params, optimizer, train_data, label='Train')
        # Validation step
        valid_loss, valid_acc, valid_auc = test(
            model,  params, optimizer, valid_data, label='Valid')

        print('epoch', idx + 1)
        print("valid_auc\t", valid_auc, "\ttrain_auc\t", train_auc)
        print("valid_acc\t", valid_acc,
              "\ttrain_acc\t", train_acc)
        print("valid_loss\t", valid_loss, "\ttrain_loss\t", train_loss)

        try_makedirs('model')
        try_makedirs(os.path.join('model', params.model))
        try_makedirs(os.path.join('model', params.model, params.save))

        all_valid_auc[idx + 1] = valid_auc
        all_train_auc[idx + 1] = train_auc
        all_valid_loss[idx + 1] = valid_loss
        all_train_loss[idx + 1] = train_loss
        all_valid_acc[idx + 1] = valid_acc
        all_train_acc[idx + 1] = train_acc

        # output the epoch with the best validation auc
        if valid_auc > best_valid_auc:
            path = os.path.join('model', params.model,
                                params.save,  file_name) + '_*'
            for i in glob.glob(path):
                os.remove(i)
            best_valid_auc = valid_auc
            best_epoch = idx+1
            torch.save({'epoch': idx,
                        'model_state_dict': model.state_dict(),
                        'optimizer_state_dict': optimizer.state_dict(),
                        'loss': train_loss,
                        },
                       os.path.join('model', params.model, params.save,
                                    file_name)+'_' + str(idx+1)
                       )
        if idx-best_epoch > 40:
            break

    try_makedirs('result')
    try_makedirs(os.path.join('result', params.model))
    try_makedirs(os.path.join('result', params.model, params.save))
    f_save_log = open(os.path.join(
        'result', params.model, params.save, file_name), 'w')
    f_save_log.write("valid_auc:\n" + str(all_valid_auc) + "\n\n")
    f_save_log.write("train_auc:\n" + str(all_train_auc) + "\n\n")
    f_save_log.write("valid_loss:\n" + str(all_valid_loss) + "\n\n")
    f_save_log.write("train_loss:\n" + str(all_train_loss) + "\n\n")
    f_save_log.write("valid_acc:\n" + str(all_valid_acc) + "\n\n")
    f_save_log.write("train_acc:\n" + str(all_train_acc) + "\n\n")
    f_save_log.close()
    return best_epoch

def test_one_dataset(params, file_name, test_data, best_epoch):
    print("\n\nStart testing ......................\n Best epoch:", best_epoch)
    model = load_model(params)

    checkpoint = torch.load(os.path.join(
        'model', params.model, params.save, file_name) + '_'+str(best_epoch))
    model.load_state_dict(checkpoint['model_state_dict'])

    test_loss, test_acc, test_auc = test(model, params, None, test_data, label='Test')
    print("\ntest_auc\t", test_auc)
    print("test_acc\t", test_acc)
    print("test_loss\t", test_loss)

    # Now Delete all the models
    path = os.path.join('model', params.model, params.save,  file_name) + '_*'
    for i in glob.glob(path):
        os.remove(i)
    return test_auc, test_acc, test_loss

def get_auc(fold_num):
    # Parse Arguments
    parser = argparse.ArgumentParser(description='Script to test KT')
    # Basic Parameters
    parser.add_argument('--max_iter', type=int, default=1000,
                        help='number of iterations')
    parser.add_argument('--train_set', type=int, default=fold_num)
    parser.add_argument('--seed', type=int, default=224, help='default seed')

    # Common parameters
    parser.add_argument('--optim', type=str, default='adam',
                        help='Default Optimizer')
    parser.add_argument('--batch_size', type=int,
                        default=24, help='the batch size')
    parser.add_argument('--lr', type=float, default=1e-5,
                        help='learning rate')
    parser.add_argument('--maxgradnorm', type=float,
                        default=-1, help='maximum gradient norm')
    parser.add_argument('--final_fc_dim', type=int, default=512,
                        help='hidden state dim for final fc layer')

    # AKT Specific Parameter
    parser.add_argument('--d_model', type=int, default=256,
                        help='Transformer d_model shape')
    parser.add_argument('--d_ff', type=int, default=1024,
                        help='Transformer d_ff shape')
    parser.add_argument('--dropout', type=float,
                        default=0.05, help='Dropout rate')
    parser.add_argument('--n_block', type=int, default=1,
                        help='number of blocks')
    parser.add_argument('--n_head', type=int, default=8,
                        help='number of heads in multihead attention')
    parser.add_argument('--kq_same', type=int, default=1)

    # AKT-R Specific Parameter
    parser.add_argument('--l2', type=float, default=1e-5, help='l2 penalty for difficulty')

    # Datasets and Model
    parser.add_argument('--model', type=str, default='akt',
                        help="combination of akt(mandatory), e_p_f_a (mandatory) separated by underscore '_'.")
    parser.add_argument('--dataset', type=str, default="assist2009")
    parser.add_argument('--test', type=bool, default=False, help='enable testing')

    params = parser.parse_args()
    dataset = params.dataset

    if dataset in {"assist2009"}:
        params.n_question = 124
        params.batch_size = 24
        params.seqlen = 400
        params.data_dir = 'data/'+dataset
        params.data_name = dataset
        params.n_pid = 19932
        params.n_tid = 8
        params.n_fid = 8
        params.n_sd = 14 #sequence_delay
        params.n_rd = 11 #repeat_delay
        params.n_xid = 816
        params.n_yid = 4

    if dataset in {"assist2017"}:
        params.batch_size = 24
        params.seqlen = 200
        params.data_dir = 'data/'+dataset
        params.data_name = dataset
        params.n_question = 102
        params.n_pid = 0#3162
        params.n_tid = 4
        params.n_fid = 7
        params.n_sd = 18 #sequence_delay
        params.n_rd = 20 #repeat_delay
        params.n_xid = 16
        params.n_yid = 6

    if dataset in {"statics"}:
        params.n_question = 1223
        params.batch_size = 24
        params.seqlen = 200
        params.data_dir = 'data/'+dataset
        params.data_name = dataset
        params.n_pid = 0
        params.n_tid = 8
        params.n_fid = 9
        params.n_sd = 16
        params.n_rd = 17
        params.n_xid = 382
        params.n_yid = 19

    if dataset in {"slepemapy"}:
        params.n_question = 1277
        params.batch_size = 24
        params.seqlen = 200
        params.data_dir = 'data/'+dataset
        params.data_name = dataset
        params.n_pid = 56030
        params.n_tid = 7
        params.n_fid = 5
        params.n_sd = 14
        params.n_rd = 15
        params.n_xid = 21
        params.n_yid = 0#56030

    params.save = params.data_name
    params.load = params.data_name

    # Setup
    dat = DATA(n_question=params.n_question, seqlen=params.seqlen, separate_char=',')

    seedNum = params.seed
    np.random.seed(seedNum)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.manual_seed(seedNum)
    np.random.seed(seedNum)
    file_name_identifier = get_file_name_identifier(params)

    ###Train- Test
    d = vars(params)
    for key in d:
        print('\t', key, '\t', d[key])

    #model path
    file_name = ''
    for item_ in file_name_identifier:
        file_name = file_name+item_[0] + str(item_[1])

    train_data_path = params.data_dir + "/" + \
                          params.data_name + "_train"+str(params.train_set)+".csv"
    valid_data_path = params.data_dir + "/" + \
                          params.data_name + "_valid"+str(params.train_set)+".csv"

    train_data = dat.load_data(train_data_path)
    valid_data = dat.load_data(valid_data_path)
    # Train and get the best episode
    best_epoch = train_one_dataset(
            params, file_name, train_data, valid_data)
    test_data_path = params.data_dir + "/" + \
                         params.data_name + "_test"+str(params.train_set)+".csv"
    test_data = dat.load_test_data(test_data_path)
    auc, acc, loss = test_one_dataset(params, file_name, test_data, best_epoch)
    return test_data[-1], auc, acc, loss


if __name__ == '__main__':
    weight_auc = 0
    weight_acc = 0
    weight_loss = 0
    total_q_num = 0
    for fold_num in range(5):
        test_q_num, auc, acc, loss= get_auc(fold_num)
        total_q_num += test_q_num
        weight_auc += test_q_num * auc
        weight_acc += test_q_num * acc
        weight_loss += test_q_num * loss
    print('AUC:\t', weight_auc / total_q_num)
    print('ACC:\t', weight_acc / total_q_num)
    print('Loss:\t', weight_loss / total_q_num)
