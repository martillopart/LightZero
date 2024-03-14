import copy
from typing import List

import gymnasium as gym
import numpy as np
from ding.envs import BaseEnv, BaseEnvTimestep
from ding.torch_utils import to_ndarray
from ding.utils import ENV_REGISTRY
from easydict import EasyDict


@ENV_REGISTRY.register('memory_lightzero')
class MemoryEnvLightZero(BaseEnv):
    """
    Overview:
        The MemoryEnvLightZero environment for LightZero, based on the Visual-Match and Key-to-Door Task from DeepMind.
    Attributes:
        config (dict): Configuration dict. Default configurations can be updated using this.
        _cfg (dict): Internal configuration dict that stores runtime configurations.
        _init_flag (bool): Flag to check if the environment is initialized.
        _env_id (str): The name of the Visual Match environment.
        _save_replay (bool): Flag to check if replays are saved.
        _max_step (int): Maximum number of steps for the environment.
    """
    config = dict(
        env_name='visual_match',  # The name of the environment, options: 'visual_match', 'key_to_door'
        # max_step=60,  # The maximum number of steps for each episode
        num_apples=10,  # Number of apples in the distractor phase
        # apple_reward=(1, 10),  # Range of rewards for collecting an apple
        # apple_reward=(1, 1),  # Range of rewards for collecting an apple
        apple_reward=(0, 0),  # Range of rewards for collecting an apple
        fix_apple_reward_in_episode=False,  # Whether to fix apple reward (DEFAULT_APPLE_REWARD) within an episode
        final_reward=10.0,  # Reward for choosing the correct door in the final phase
        respawn_every=300,  # Respawn interval for apples
        crop=True,  # Whether to crop the observation
        max_frames={
            "explore": 15,
            "distractor": 30,
            "reward": 15
        },  # Maximum frames per phase
    )

    @classmethod
    def default_config(cls: type) -> EasyDict:
        cfg = EasyDict(copy.deepcopy(cls.config))
        cfg.cfg_type = cls.__name__ + 'Dict'
        return cfg

    def __init__(self, cfg: dict) -> None:
        """
        Overview:
            Initialize the environment.
        Arguments:
            - cfg (:obj:`dict`): Configuration dict.
        """
        self._cfg = cfg
        self._init_flag = False
        self._save_replay = False

    def reset(self) -> np.ndarray:
        """
        Overview:
            Reset the environment and return the initial observation.
        Returns:
            - obs (:obj:`np.ndarray`): Initial observation from the environment.
        """
        self._seed = 0
        if not self._init_flag:
            if hasattr(self, '_seed') and hasattr(self, '_dynamic_seed') and self._dynamic_seed:
                np_seed = 100 * np.random.randint(1, 1000)
                self._seed = self._seed + np_seed
                self._rng = np.random.RandomState(self._seed)
            elif hasattr(self, '_seed'):
                self._rng = np.random.RandomState(self._seed)

            if self._cfg.env_name == 'visual_match':
                from zoo.memory.envs.pycolab_tvt.visual_match import Game, PASSIVE_EXPLORE_GRID
                self._game = Game(
                    self._rng,
                    num_apples=self._cfg.num_apples,
                    apple_reward=self._cfg.apple_reward,
                    fix_apple_reward_in_episode=self._cfg.fix_apple_reward_in_episode,
                    final_reward=self._cfg.final_reward,
                    respawn_every=self._cfg.respawn_every,
                    crop=self._cfg.crop,
                    max_frames=self._cfg.max_frames,
                    EXPLORE_GRID=PASSIVE_EXPLORE_GRID,
                )
            elif self._cfg.env_name == 'key_to_door':
                from zoo.memory.envs.pycolab_tvt.key_to_door import Game, REWARD_GRID_SR, MAX_FRAMES_PER_PHASE_SR
                self._game = Game(
                    self._rng,
                    num_apples=self._cfg.num_apples,
                    apple_reward=self._cfg.apple_reward,
                    fix_apple_reward_in_episode=self._cfg.fix_apple_reward_in_episode,
                    final_reward=self._cfg.final_reward,
                    respawn_every=self._cfg.respawn_every,
                    crop=self._cfg.crop,
                    max_frames=self._cfg.max_frames,
                    REWARD_GRID=REWARD_GRID_SR,
                )

            self._episode = self._game.make_episode()

            self._observation_space = gym.spaces.Box(0, 1, shape=(1, 5, 5), dtype='float32')
            self._action_space = gym.spaces.Discrete(self._game.num_actions)
            self._reward_space = gym.spaces.Box(low=-float('inf'), high=float('inf'), shape=(1,), dtype=np.float32)

            self._init_flag = True

        self._current_step = 0
        self._eval_episode_return = 0
        obs, _, _ = self._episode.its_showtime()
        obs = obs[0].reshape(1, 5, 5)
        obs = to_ndarray(obs)
        action_mask = np.ones(self.action_space.n, 'int8')
        obs = {'observation': obs, 'action_mask': action_mask, 'to_play': -1}

        return obs

    def close(self) -> None:
        """
        Close the environment.
        """
        self._init_flag = False

    def seed(self, seed: int, dynamic_seed: bool = True) -> None:
        """
        Set the seed for the environment's random number generator. Can handle both static and dynamic seeding.
        """
        self._seed = seed
        self._dynamic_seed = dynamic_seed
        np.random.seed(self._seed)
        self._rng = np.random.RandomState(self._seed)

    def step(self, action: np.ndarray) -> BaseEnvTimestep:
        """
        Overview:
            Perform a step in the environment using the provided action, and return the next state of the environment.
        Arguments:
            - action (:obj:`np.ndarray`): The action to be performed in the environment.
        Returns:
            - timestep (:obj:`BaseEnvTimestep`): An object containing the new observation, reward, done flag,
              and info dictionary.
        """
        if isinstance(action, np.ndarray) and action.shape == (1,):
            action = action.squeeze()  # 0-dim array

        observation, reward, _ = self._episode.play(action)
        observation = observation[0].reshape(1, 5, 5)

        self._current_step += 1
        self._eval_episode_return += reward
        done = self._episode.game_over

        info = {}
        if done:
            # TODO
            info['eval_episode_return'] = self._eval_episode_return
            info['success'] = 1 if reward == self._cfg.final_reward else 0
            info['eval_episode_return'] = info['success']

        observation = to_ndarray(observation)
        reward = to_ndarray([reward])
        action_mask = np.ones(self.action_space.n, 'int8')
        observation = {'observation': observation, 'action_mask': action_mask, 'to_play': -1}

        return BaseEnvTimestep(observation, reward, done, info)

    def random_action(self) -> np.ndarray:
        """
        Generate a random action using the action space's sample method. Returns a numpy array containing the action.
        """
        random_action = self.action_space.sample()
        random_action = to_ndarray([random_action], dtype=np.int64)
        return random_action

    @property
    def observation_space(self) -> gym.spaces.Space:
        return self._observation_space

    @property
    def action_space(self) -> gym.spaces.Space:
        return self._action_space

    @property
    def reward_space(self) -> gym.spaces.Space:
        return self._reward_space

    @staticmethod
    def create_collector_env_cfg(cfg: dict) -> List[dict]:
        collector_env_num = cfg.pop('collector_env_num')
        cfg = copy.deepcopy(cfg)
        cfg.is_train = True
        return [cfg for _ in range(collector_env_num)]

    @staticmethod
    def create_evaluator_env_cfg(cfg: dict) -> List[dict]:
        evaluator_env_num = cfg.pop('evaluator_env_num')
        cfg = copy.deepcopy(cfg)
        cfg.is_train = False
        return [cfg for _ in range(evaluator_env_num)]

    def __repr__(self):
        return "Memory Env of LightZero"