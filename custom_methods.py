"""
This python file is used to save special methods in the research

"""


import torch
import numpy as np
import os
from scipy.stats import pearsonr

# method
def chack_eva_type():
    pass

def hessian(model):
        train_x, train_y = model.np2tensor(model.dataset['train'].get_batch())
        train_loss = model.loss_fn(model.model(train_x), train_y)
        fir_grads = torch.autograd.grad(train_loss, model.model.parameters(), create_graph=True)
        fir_grads = torch.cat([grad.flatten() for grad in fir_grads])

        sec_grads = []
        for grad in fir_grads:
            partial_grad = torch.autograd.grad(grad, model.model.parameters(), create_graph=True)
            partial_grad = torch.cat([grad.flatten() for grad in partial_grad])
            sec_grads.append(partial_grad)
        sec_grads = torch.stack(sec_grads)
        return sec_grads

def inverse_matrix(matrix):
    if np.linalg.det(matrix) == 0:
        return np.linalg.pinv(matrix)
    inverse_matrix = np.identity(len(matrix))
    for I_col in range(len(matrix)):
        inverse_matrix[I_col, :] /= matrix[I_col, I_col]
        matrix[I_col, :] /= matrix[I_col, I_col]
        for row in range(len(matrix)):
            if I_col != row:
                inverse_matrix[row, :] -= inverse_matrix[I_col, :]* matrix[row, I_col]
                matrix[row, :] -= matrix[I_col, :]* matrix[row, I_col]
    return inverse_matrix

def predict_on_single(model=None, eva_id=None, eva_set_type='test', inf_id=None):
        """This method predict difference will appear on the evaluate single point performance(ex: loss, y)
        after add one single point in train set. (add_one_point_model - origin_model)

        Args:
            model (_type_, optional): _description_. Defaults to None.
            eva_id (_type_, optional): _description_. Defaults to None.
            eva_set_type (_type_, optional): _description_. Defaults to 'test'.
            inf_id (_type_, optional): _description_. Defaults to None.
        """
        assert model is not None
        assert eva_id is not None
        assert eva_set_type in ['train', 'test', 'valid']
        assert inf_id is not None
        eva_x, eva_y = model.np2tensor(model.dataset[eva_set_type].get_by_idxs(eva_id))
        eva_loss = model.loss_fn(model.model(eva_x), eva_y)
        eva_grad = torch.autograd.grad(eva_loss, model.model.parameters())
        eva_grad = torch.cat([grad.flatten() for grad in eva_grad]).numpy()
        inverse_H = inverse_matrix(hessian(model).detach().numpy())

        inf_x, inf_y = model.np2tensor(model.dataset['train'].get_by_idxs(inf_id))
        inf_loss = model.loss_fn(model.model(inf_x), inf_y)
        inf_grad = torch.autograd.grad(inf_loss, model.model.parameters())
        inf_grad = torch.cat([grad.flatten() for grad in inf_grad]).numpy()

        inf = -np.matmul(eva_grad, np.matmul(inverse_H, inf_grad))/ model.dataset['train'].num_examples
        return inf

def predict_on_batch(model=None, eva_set_type='test', inf_id=None):
    """This method predict difference will appear on the evaluate dataset performance(ex: loss)
        after add one single point in train set. (add_one_point_model - origin_model)

    Args:
        verbose (bool, optional): _description_. Defaults to True.
        target_fn (_type_, optional): _description_. Defaults to None.
        test_id (_type_, optional): _description_. Defaults to None.
        removed_id (_type_, optional): _description_. Defaults to None.
    """
    assert model is not None
    assert eva_set_type in ['train', 'test', 'valid']
    assert inf_id is not None

    eva_x, eva_y = model.np2tensor(model.dataset[eva_set_type].get_batch())
    eva_loss = model.loss_fn(model.model(eva_x), eva_y)
    eva_grad = torch.autograd.grad(eva_loss, model.model.parameters())
    eva_grad = torch.cat([grad.flatten() for grad in eva_grad]).numpy()
    inverse_H = inverse_matrix(hessian(model).detach().numpy())

    inf_x, inf_y = model.np2tensor(model.dataset['train'].get_by_idxs(inf_id))
    inf_loss = model.loss_fn(model.model(inf_x), inf_y)
    inf_grad = torch.autograd.grad(inf_loss, model.model.parameters())
    inf_grad = torch.cat([grad.flatten() for grad in inf_grad]).numpy()

    inf = -np.matmul(eva_grad, np.matmul(inverse_H, inf_grad)) / model.dataset['train'].num_examples
    return inf


# experience
def experiment_get_correlation(model, configs, eva_set_type='test', eva_id=None):
    """This method gets the correlation between predict influences and real influences
    of all current sample points.

    Args:
        model (Model): An model object
        configs (argparse.Namespace): An argparse.Namespace object includes all configurations.
        eva_set_type(list): An List of strings represents all types of datasets to be evaluated.
        eva_id(int): An integer represents the id of data point to be evaluated.
    """
    assert eva_set_type in ['train', 'test', 'valid']
    pred_diffs = []
    real_diffs = []

    # get original model
    checkpoint = model.train(
        num_epoch=configs.num_epoch_train,
        verbose=True,
        checkpoint_name="Test"
    )
    if eva_id is None:
        eva_x, eva_y = model.np2tensor(model.dataset[eva_set_type].get_batch())
    else:
        eva_x, eva_y = model.np2tensor(model.dataset[eva_set_type].get_by_idxs(eva_id))
    ori_loss = model.loss_fn(model.model(eva_x), eva_y).item()

    for inf_id in range(model.dataset['train'].num_examples):
        print("processing point {}/{}".format(inf_id+1, model.dataset['train'].num_examples))
        if eva_id is None:
            pred_diffs.append(predict_on_batch(
                model=model,
                eva_set_type=eva_set_type,
                inf_id=inf_id
            ))
        else:
            pred_diffs.append(predict_on_single(
                model=model,
                eva_set_type=eva_set_type,
                eva_id=eva_id,
                inf_id=inf_id  
            ))
        remain_ids = np.append(model.remain_ids, np.array([inf_id]))
        # remain_ids = np.setdiff1d(model.remain_ids, np.array([inf_id]))
        model.reset_train_dataset(remain_ids)
        model.train(
            num_epoch=configs.num_epoch_train,
            checkpoint_name="eva{}_+inf{}".format(eva_id, inf_id)
        )
        re_loss = model.loss_fn(model.model(eva_x), eva_y).item()
        real_diffs.append(re_loss - ori_loss)
        model.load_model(checkpoint)
        
    real_diffs = np.array(real_diffs)
    pred_diffs = np.array(pred_diffs)
    print('Correlation is %s' % pearsonr(real_diffs, pred_diffs)[0])
    if os.path.exists(configs.experiment_save_dir) is False:
            os.makedirs(configs.experiment_save_dir)
    np.savez(
        '{}/result-{}-{}.npz'.format(configs.experiment_save_dir, configs.model, configs.dataset),
        real_diffs=real_diffs,
        pred_diffs=pred_diffs,
    )

def experiment_remove_all_negtive(model, configs, eva_set_type='test', eva_id=None, based_pred=True):
    assert eva_set_type in ['train', 'test', 'valid']

    diffs = np.array([-1])
    samples_diff_dic = {}
    while len(diffs<=0) > 0:
        # get original checkpoint
        model.train(
                num_epoch=configs.num_epoch_train,
                load_checkpoint=configs.load_checkpoint,
                save_checkpoints=configs.save_checkpoint,
                checkpoint_name="ori_num{}".format(model.dataset['train'].num_examples)
        )
        if not based_pred:
            # get test data
            if eva_id is None:
                test_x, test_y = model.np2tensor(model.dataset['test'].get_batch())
            else:
                test_x, test_y = model.np2tensor(model.dataset['test'].get_by_idxs(eva_id))
            ori_loss = model.loss_fn(model.model(test_x), test_y).item()
        
        diffs = np.array([])
        for inf_id in range(model.dataset['train'].x.shape[0]):
            print("Remain {} data points".format(model.dataset['train'].num_examples))
            print("processing point {}/{}".format(inf_id+1, model.dataset['train'].x.shape[0]))
            if based_pred:
                if eva_id is None:
                    diffs = np.append(diffs, -predict_on_batch(
                        model=model,
                        eva_set_type=eva_set_type,
                        inf_id=inf_id
                    ))
                else:
                    diffs = np.append(diffs, -predict_on_single(
                        model=model,
                        eva_id=eva_id,
                        eva_set_type=eva_set_type,
                        inf_id=inf_id
                    ))
            else:
                if inf_id in remain_ids:
                    remain_ids = np.setdiff1d(model.remain_ids, np.array([inf_id]))
                    model.reset_train_dataset(remain_ids)
                    model.train(
                        num_epoch=configs.num_epoch_train,
                        load_checkpoint=configs.load_checkpoint,
                        save_checkpoints=configs.save_checkpoint,
                        verbose=False,
                        checkpoint_name="eva{}_inf{}_num{}".format(eva_id, inf_id, model.dataset['train'].num_examples),
                        plot=configs.plot
                    )
                    re_loss = model.loss_fn(model.model(test_x), test_y).item()
                    diffs = np.append(diffs, (re_loss - ori_loss))
                else:
                    diffs = np.append(diffs, np.nan)
            if inf_id in samples_diff_dic.keys():
                samples_diff_dic[inf_id].append(diffs[inf_id])
            else:
                samples_diff_dic[inf_id] = [diffs[inf_id]]
        copy_diffs = diffs[model.remain_ids]
        model.remain_ids = model.remain_ids[np.argsort(copy_diffs)]
        print("remove point {}".format(model.remain_ids[0]))
        model.reset_train_dataset(model.remain_ids[1:])
        diffs = diffs[model.remain_ids]
    if os.path.exists(configs.experiment_save_dir) is False:
            os.makedirs(configs.experiment_save_dir)
    np.savez(
        '{}/remove_all_negtive-{}-{}.npz'.format(configs.experiment_save_dir, configs.model, configs.dataset),
        ids=model.remain_ids,
        samples_diff_dic=samples_diff_dic
    )

def experiment_predict_distribution(model, configs, precent_to_keep=1.0, epoch=100, eva_set_type='test'):
    all_select_ids = []
    samples_diff_dic = {}
    remain_num = int(model.dataset['train'].x.shape[0]*precent_to_keep)
    for i in range(epoch):
        remain_ids = np.random.choice(np.arange(model.dataset['train'].x.shape[0]), size=remain_num, replace=False)
        while remain_ids in all_select_ids:
            remain_ids = np.random.choice(np.arange(model.dataset['train'].x.shape[0]), size=remain_num, replace=False)
        all_select_ids.append(remain_ids)
        model.reset_train_dataset(remain_ids)
        model.train(
            num_epoch=configs.num_epoch_train,
            checkpoint_name="rand{}_num{}".format(i, remain_num)
        )
        for inf_id in range(model.dataset['train'].x.shape[0]):
            if inf_id not in samples_diff_dic.keys():
                samples_diff_dic[inf_id] = [predict_on_batch(model, eva_set_type, inf_id)]
            else:
                samples_diff_dic[inf_id].append(predict_on_batch(model, eva_set_type, inf_id))
    if os.path.exists(configs.experiment_save_dir) is False:
            os.makedirs(configs.experiment_save_dir)
    np.savez(
        '{}/rand{}-{}-{}.npz'.format(configs.experiment_save_dir, precent_to_keep, configs.model, configs.dataset),
        point_diffs=samples_diff_dic
    )

def experiment_possible_higher_accuracy(model, configs, experiment_configs):
    
    for eva_set_type in experiment_configs["eva_sets"]:
        assert eva_set_type in ['train', 'test', 'valid']
    
    if configs.task_num == 1:
        all_ori_accuracies = []
        model.train(num_epoch=configs.num_epoch_train, checkpoint_name='ori', verbose=True)
        for eva_type in experiment_configs["eva_sets"]:
            eva_x, eva_y = model.np2tensor(model.dataset[eva_type].get_batch())
            eva_diff = model.model(eva_x) - eva_y
            all_ori_accuracies.append(len(eva_diff[torch.abs(eva_diff)<0.5])/len(eva_diff))
        if os.path.exists(configs.experiment_save_dir) is False:
            os.makedirs(configs.experiment_save_dir)
        np.savez(
            '{}/{}_task{}.npz'.format(configs.experiment_save_dir, configs.dataset, configs.task_num),
            all_ori_accuracies=all_ori_accuracies
        )
    else:
        # {dataset}_task{task_num} for each single task
        all_ids_this_task = np.load('{}/{}/{}_task{}.npz'.format(configs.aid_dir, configs.experiment, configs.dataset, configs.task_num) , allow_pickle=True)['all_ids_this_task']
        performance = {}
        for i, remain_ids in enumerate(all_ids_this_task):
            model.reset_train_dataset(remain_ids)
            model.train(
                num_epoch=configs.num_epoch_train,
                checkpoint_name='rand{}_num{}'.format(i+(configs.task_num-2)*10, len(remain_ids))
            )
            for eva_type in experiment_configs["eva_sets"]:
                eva_x, eva_y = model.np2tensor(model.dataset[eva_type].get_batch())
                eva_diff = model.model(eva_x) - eva_y
                if eva_type in performance.keys():
                    performance[eva_type].append(len(eva_diff[torch.abs(eva_diff)<0.5])/len(eva_diff))
                else:
                    performance[eva_type] = [len(eva_diff[torch.abs(eva_diff)<0.5])/len(eva_diff)]
        if os.path.exists(configs.experiment_save_dir) is False:
            os.makedirs(configs.experiment_save_dir)
        np.savez(
            '{}/{}_task{}.npz'.format(configs.experiment_save_dir, configs.dataset, configs.task_num),
            all_ori_accuracies=all_ori_accuracies
        )

def experiment_small_model_select_points(model, configs, experiment_configs):
    """_summary_

    Args:
        model (Model): An model object
        configs (argparse.Namespace): An argparse.Namespace object includes all configurations.
        experiment_configs(dict): An dictionary of experiment_configs.
    """
    def whole_data_accuracies_task():
        """
        This task get accuracies of a big model(with all training data) on all eva_sets.
        
        this task can be tested by the following code:
            python -u main.py --experiment experiment_small_model_select_points --dataset fraud_detection --task_num 1
        """
        
        all_ori_accuracies = []
        model.train(num_epoch=configs.num_epoch_train, checkpoint_name='ori', verbose=True)
        for eva_type in experiment_configs["eva_sets"]:
            eva_x, eva_y = model.np2tensor(model.dataset[eva_type].get_batch())
            eva_diff = model.model(eva_x) - eva_y
            all_ori_accuracies.append(len(eva_diff[torch.abs(eva_diff)<0.5])/len(eva_diff))
        if os.path.exists(configs.experiment_save_dir) is False:
            os.makedirs(configs.experiment_save_dir)
        np.savez(
            '{}/{}_task{}.npz'.format(configs.experiment_save_dir, configs.dataset, configs.task_num),
            all_ori_accuracies=all_ori_accuracies
        )
    
    def small_model_task():
        """
        This task evaluates the performance of small model with well selected data. The task step is following:
            1. training {num_rand_model} small models with randomly selected data.
            2. Get indexes of selected data according to the influence value predicted by previous models.
                the indexes of negative influence value(adding the point has negative effect on loss) will be remained.
                two method will be applied for selecting data points: mean value method, vote method
            3. training a small model with well selected data
            4. get the accuracy of the model on all eva_sets
        
        this task can be tested by the following code:
            python -u main.py --experiment experiment_small_model_select_points --dataset fraud_detection --task_num 2
        """
        performance = {}
        remain_num = int(model.dataset['train'].x.shape[0]*experiment_configs["remain_percent"])

        for repeat_epoch in range(1, experiment_configs["repeat_times"]+1):
            all_infs = []
            for model_id in range(1, experiment_configs["num_rand_model"]+1):
                remain_ids = np.random.choice(np.arange(model.dataset['train'].x.shape[0]), size=remain_num, replace=False)
                # training model with randomly selected training data
                model.reset_train_dataset(remain_ids)
                model.train(
                    num_epoch=configs.num_epoch_train,
                    checkpoint_name='rand{}_model{}_num{}'.format(repeat_epoch+(configs.task_num-2)*experiment_configs['repeat_times'], model_id, len(remain_ids)),
                    save_checkpoints=True
                )
                # get inf value of all data points
                eva_set_type = "test"
                infs = np.array([])
                for inf_id in range(model.dataset['train'].x.shape[0]):
                    print("processing point {}/{}".format(inf_id+1, model.dataset['train'].x.shape[0]))
                    infs = np.append(infs, -predict_on_batch(
                            model=model,
                            eva_set_type=eva_set_type,
                            inf_id=inf_id
                        ))
                all_infs.append(infs)
            all_infs = np.stack(all_infs)
            if experiment_configs["data_selecting_method"] == "mean":
                all_infs = np.mean(all_infs, axis=0)
                remain_ids = np.where(all_infs < 0)[0]
            elif experiment_configs["data_selecting_method"] == "vote":
                remain_ids = np.count_nonzero(all_infs > 0, axis=0)
                input(remain_ids)
                input("working on this")
            else:
                assert NotImplementedError
            # training model with selected training data according to inf predicted by previous randomly-selected-data model
            model.reset_train_dataset(remain_ids)
            model.train(
                num_epoch=configs.num_epoch_train,
                checkpoint_name='select{}_num{}'.format(repeat_epoch+(configs.task_num-2)*experiment_configs['repeat_times'], len(remain_ids)),
                save_checkpoints=True
            )
            # evaluate the accuracies of the model on all eva_set
            for eva_type in experiment_configs["eva_sets"]:
                eva_x, eva_y = model.np2tensor(model.dataset[eva_type].get_batch())
                eva_diff = model.model(eva_x) - eva_y
                if eva_type in performance.keys():
                    performance[eva_type].append(len(eva_diff[torch.abs(eva_diff)<0.5])/len(eva_diff))
                else:
                    performance[eva_type] = [len(eva_diff[torch.abs(eva_diff)<0.5])/len(eva_diff)]
        # save the result
        if os.path.exists(configs.experiment_save_dir) is False:
            os.makedirs(configs.experiment_save_dir)
        np.savez(
            '{}/{}_task{}.npz'.format(configs.experiment_save_dir, configs.dataset, configs.task_num),
            performance=performance
        )
    
    for eva_set_type in experiment_configs["eva_sets"]:
        assert eva_set_type in ['train', 'test', 'valid']
        
    if configs.task_num == 1:
        whole_data_accuracies_task()

    else:
        small_model_task()