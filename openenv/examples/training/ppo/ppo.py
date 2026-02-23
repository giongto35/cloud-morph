"""CleanRL-style PPO with Nature-CNN agent. No stable-baselines3 dependency.

Provides:
- CNNAgent: Nature-CNN (32->64->64 conv) -> 512 FC -> policy + value heads
- ppo_update(): Clipped PPO with GAE, 4 epochs, minibatch_size=64
- compute_gae(): Generalized Advantage Estimation
"""

import numpy as np
import torch
import torch.nn as nn
from torch.distributions import Categorical


def layer_init(layer, std=np.sqrt(2), bias_const=0.0):
    nn.init.orthogonal_(layer.weight, std)
    nn.init.constant_(layer.bias, bias_const)
    return layer


class CNNAgent(nn.Module):
    """Nature-CNN policy+value network for 84x84x3 RGB observations."""

    def __init__(self, num_actions=35):
        super().__init__()
        # Store conv layers separately for activation extraction
        self.conv1 = layer_init(nn.Conv2d(3, 32, 8, stride=4))
        self.conv2 = layer_init(nn.Conv2d(32, 64, 4, stride=2))
        self.conv3 = layer_init(nn.Conv2d(64, 64, 3, stride=1))
        self.fc = layer_init(nn.Linear(64 * 7 * 7, 512))

        # Full sequential for forward pass
        self.network = nn.Sequential(
            self.conv1, nn.ReLU(),
            self.conv2, nn.ReLU(),
            self.conv3, nn.ReLU(),
            nn.Flatten(),
            self.fc, nn.ReLU(),
        )
        self.actor = layer_init(nn.Linear(512, num_actions), std=0.01)
        self.critic = layer_init(nn.Linear(512, 1), std=1)

    def _preprocess(self, x):
        """(B, H, W, C) uint8 -> (B, C, H, W) float32"""
        return x.permute(0, 3, 1, 2).float() / 255.0

    def get_value(self, x):
        x = self._preprocess(x)
        return self.critic(self.network(x))

    def get_action_and_value(self, x, action=None):
        x = self._preprocess(x)
        hidden = self.network(x)
        logits = self.actor(hidden)
        probs = Categorical(logits=logits)
        if action is None:
            action = probs.sample()
        return action, probs.log_prob(action), probs.entropy(), self.critic(hidden)

    @torch.no_grad()
    def get_activations(self, x):
        """Run forward pass and return intermediate conv activations + action probs.

        Args:
            x: (B, H, W, C) uint8 tensor

        Returns dict with:
            conv1: (B, 32, 20, 20) tensor
            conv2: (B, 64, 9, 9) tensor
            conv3: (B, 64, 7, 7) tensor
            fc: (B, 512) tensor
            action_probs: (B, num_actions) tensor
            value: (B, 1) tensor
        """
        x = self._preprocess(x)
        a1 = torch.relu(self.conv1(x))
        a2 = torch.relu(self.conv2(a1))
        a3 = torch.relu(self.conv3(a2))
        flat = a3.flatten(1)
        fc_out = torch.relu(self.fc(flat))
        logits = self.actor(fc_out)
        value = self.critic(fc_out)
        probs = torch.softmax(logits, dim=-1)
        return {
            "conv1": a1,   # (B, 32, 20, 20)
            "conv2": a2,   # (B, 64, 9, 9)
            "conv3": a3,   # (B, 64, 7, 7)
            "fc": fc_out,  # (B, 512)
            "action_probs": probs,
            "value": value,
        }


def compute_gae(rewards, values, dones, next_value, gamma=0.99, gae_lambda=0.95):
    """Compute Generalized Advantage Estimation.

    Args:
        rewards: (T,) numpy array
        values: (T,) numpy array
        dones: (T,) numpy array
        next_value: scalar
        gamma: discount factor
        gae_lambda: GAE lambda

    Returns:
        advantages: (T,) numpy array
        returns: (T,) numpy array
    """
    T = len(rewards)
    advantages = np.zeros(T, dtype=np.float32)
    last_gae = 0.0
    for t in reversed(range(T)):
        if t == T - 1:
            next_val = next_value
        else:
            next_val = values[t + 1]
        next_non_terminal = 1.0 - dones[t]
        delta = rewards[t] + gamma * next_val * next_non_terminal - values[t]
        advantages[t] = last_gae = delta + gamma * gae_lambda * next_non_terminal * last_gae
    returns = advantages + values
    return advantages, returns


def ppo_update(
    agent,
    optimizer,
    obs,         # (T, 84, 84, 3) uint8 tensor
    actions,     # (T,) int64 tensor
    log_probs,   # (T,) float32 tensor
    advantages,  # (T,) float32 tensor
    returns,     # (T,) float32 tensor
    clip_coef=0.2,
    vf_coef=0.5,
    ent_coef=0.01,
    max_grad_norm=0.5,
    update_epochs=4,
    minibatch_size=64,
):
    """Run PPO update on a batch of rollout data.

    Returns dict with loss stats.
    """
    batch_size = obs.shape[0]
    # Normalize advantages
    adv_mean = advantages.mean()
    adv_std = advantages.std() + 1e-8
    advantages = (advantages - adv_mean) / adv_std

    total_pg_loss = 0.0
    total_vf_loss = 0.0
    total_entropy = 0.0
    num_updates = 0

    for _epoch in range(update_epochs):
        indices = np.random.permutation(batch_size)
        for start in range(0, batch_size, minibatch_size):
            end = start + minibatch_size
            mb_idx = indices[start:end]

            mb_obs = obs[mb_idx]
            mb_actions = actions[mb_idx]
            mb_log_probs = log_probs[mb_idx]
            mb_advantages = advantages[mb_idx]
            mb_returns = returns[mb_idx]

            _, new_log_probs, entropy, new_values = agent.get_action_and_value(
                mb_obs, mb_actions
            )
            new_values = new_values.squeeze(-1)

            # Policy loss (clipped)
            ratio = torch.exp(new_log_probs - mb_log_probs)
            pg_loss1 = -mb_advantages * ratio
            pg_loss2 = -mb_advantages * torch.clamp(ratio, 1 - clip_coef, 1 + clip_coef)
            pg_loss = torch.max(pg_loss1, pg_loss2).mean()

            # Value loss
            vf_loss = ((new_values - mb_returns) ** 2).mean()

            # Entropy bonus
            entropy_loss = entropy.mean()

            loss = pg_loss + vf_coef * vf_loss - ent_coef * entropy_loss

            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(agent.parameters(), max_grad_norm)
            optimizer.step()

            total_pg_loss += pg_loss.item()
            total_vf_loss += vf_loss.item()
            total_entropy += entropy_loss.item()
            num_updates += 1

    return {
        "policy_loss": total_pg_loss / max(num_updates, 1),
        "value_loss": total_vf_loss / max(num_updates, 1),
        "entropy": total_entropy / max(num_updates, 1),
    }
