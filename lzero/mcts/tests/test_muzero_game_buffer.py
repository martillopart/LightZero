import numpy as np
import pytest
import torch
from ding.config import compile_config
from ding.policy import create_policy
from huggingface_hub import hf_hub_url, cached_download

from lzero.mcts.buffer.game_buffer_efficientzero import MuZeroGameBuffer
from lzero.model.muzero_model import MuZeroModel as Model

# 根据测试模式，导入配置
test_mode_type = 'conv'
if test_mode_type == 'conv':
    from lzero.policy.tests.config.atari_muzero_config_for_test import atari_muzero_config as cfg
    from lzero.policy.tests.config.atari_muzero_config_for_test import atari_muzero_create_config as create_cfg
elif test_mode_type == 'mlp':
    from lzero.policy.tests.config.cartpole_muzero_config_for_test import cartpole_muzero_config as cfg
    from lzero.policy.tests.config.cartpole_muzero_config_for_test import \
        cartpole_muzero_create_config as create_cfg

# 创建模型
model = Model(**cfg.policy.model)

# 配置设备
if cfg.policy.cuda and torch.cuda.is_available():
    cfg.policy.device = 'cuda'
else:
    cfg.policy.device = 'cpu'

# 编译配置
cfg = compile_config(cfg, seed=0, env=None, auto=True, create_cfg=create_cfg, save_cfg=True)

# 将模型移至指定设备并设置为评估模式
model.to(cfg.policy.device)
model.eval()

# 创建策略
policy = create_policy(cfg.policy, model=model, enable_field=['learn', 'collect', 'eval'])

# 初始化 replay buffer
replay_buffer = MuZeroGameBuffer(cfg.policy)

# 从 Hugging Face上获取测试数据的下载链接
url = hf_hub_url("puyuan1996/pong_muzero_2episodes_gsl400_v0.0.4", "pong_muzero_2episodes_gsl400_v0.0.4.npy",
                 repo_type='dataset')
# 下载并缓存文件
local_filepath = cached_download(url)
# 加载.npy文件
data = np.load(local_filepath, allow_pickle=True)

# 向 replay buffer 添加数据
replay_buffer.push_game_segments(data)
# 如果 replay buffer 满了，移除最旧的数据
replay_buffer.remove_oldest_data_to_fit()


@pytest.mark.unittest
def test_sample_orig_data():
    # 从 replay buffer 采样数据
    train_data = replay_buffer.sample(cfg.policy.batch_size, policy)

    # 输出采样到的数据
    print(train_data)

    # a batch contains the current_batch and the target_batch
    [current_batch, target_batch] = train_data

    [batch_rewards, batch_target_values, batch_target_policies] = target_batch
    assert batch_rewards.shape == (cfg.policy.batch_size, cfg.policy.num_unroll_steps + 1)
    assert batch_target_values.shape == (cfg.policy.batch_size, cfg.policy.num_unroll_steps + 1)
    assert batch_target_policies.shape == (
        cfg.policy.batch_size, cfg.policy.num_unroll_steps + 1, cfg.policy.model.action_space_size)

    [batch_obs, batch_action, batch_mask, batch_index, batch_weights, batch_make_time] = current_batch

    assert batch_obs.shape == (cfg.policy.batch_size, cfg.policy.model.frame_stack_num + cfg.policy.num_unroll_steps,
                               cfg.policy.model.observation_shape[1], cfg.policy.model.observation_shape[2])
    assert batch_action.shape == (cfg.policy.batch_size, cfg.policy.num_unroll_steps)
    assert batch_mask.shape == (cfg.policy.batch_size, cfg.policy.num_unroll_steps + 1)
    assert batch_index.shape == (cfg.policy.batch_size,)
    assert batch_weights.shape == (cfg.policy.batch_size,)
    assert batch_make_time.shape == (cfg.policy.batch_size,)