import os
import glob
import hydra
import matplotlib.pyplot as plt
from omegaconf import DictConfig
from models.td3 import TD3
from environments.quad_env import QuadEnv
from utils.replay_buffer import ReplayBuffer
import numpy as np
import re

@hydra.main(version_base="1.2", config_path="../configs", config_name="config")
def main(cfg: DictConfig):

    print("Start Training")

    # Create checkpoint directory
    os.makedirs(cfg.logging.save_dir, exist_ok=True)

    # Initialize environment with training-specific rendering
    cfg.environment.render_mode = cfg.training.render_mode
    env = QuadEnv(cfg.environment, cfg.rewards)

    # Get state and action dimensions from the environment
    state_dim = env.observation_space.shape[0]
    action_dim = env.action_space.shape[0]

    # Initialize TD3 model and replay buffer
    model = TD3(cfg.model, env)

    episode_start = handle_checkpoints(model, cfg.logging.save_dir,cfg.training)

    replay_buffer = ReplayBuffer(cfg.model.replay_buffer_size, state_dim, action_dim)

    # Warm-up phase: Populate the buffer with random actions
    warmup_steps = cfg.training.warmup_steps
    print(f"Starting warm-up phase with {warmup_steps} steps...")
    state, _ = env.reset()
    for _ in range(warmup_steps):
        action = env.action_space.sample()  # Random action
        next_state, reward, terminated, truncated, _ = env.step(action)
        done = terminated or truncated

        replay_buffer.add(state, action, reward, next_state, done)
        state = next_state if not done else env.reset()[0]

    print("Warm-up phase complete. Starting training...")

    # Training loop
    rewards, critic1_losses, critic2_losses = [], [], []
    for episode in range(episode_start,cfg.training.episodes):
        state, _ = env.reset()
        total_reward = 0

        for step in range(cfg.training.max_steps):
            action = model.select_action(state)
            next_state, reward, terminated, truncated, _ = env.step(action)
            done = terminated or truncated

            replay_buffer.add(state, action, reward, next_state, done)
            critic1_loss, critic2_loss = model.train(replay_buffer)
            critic1_losses.append(float(critic1_loss))
            critic2_losses.append(float(critic2_loss))

            state = next_state
            total_reward += reward
            if done:
                break

        rewards.append(total_reward)

        if (episode + 1) % cfg.logging.log_freq == 0:
            print(f"Episode {episode + 1}/{cfg.training.episodes}: Total Reward = {total_reward:.2f}")

        if (episode + 1) % cfg.logging.checkpoint_freq == 0:
            model.save(os.path.join(cfg.logging.save_dir, f"episode_{episode + 1}"))

    env.close()
    plot_metrics(rewards, critic1_losses, critic2_losses, cfg.logging.metrics_file)




def handle_checkpoints(model, save_dir, training_cfg):
    """
    Handle checkpoints for resuming or overwriting training.

    Args:
        model: The model object to load weights into.
        save_dir (str): Directory where checkpoints are stored.
        training_cfg: Configuration object with `resume` and `overwrite` attributes.

    Returns:
        int: The episode index of the latest checkpoint, or None if no checkpoint is found.
    """
    latest_episode = 0

    if training_cfg.resume and not training_cfg.overwrite:
        # Find all actor checkpoint files
        actor_checkpoints = [
            f for f in glob.glob(f"{save_dir}/*_actor.pth") if re.search(r"episode_(\d+)_actor\.pth$", f)
        ]
        if actor_checkpoints:
            # Extract the base path and episode index
            latest_checkpoint = max(
                actor_checkpoints,
                key=lambda x: int(re.search(r"episode_(\d+)", x).group(1))
            )
            latest_episode = int(re.search(r"episode_(\d+)", latest_checkpoint).group(1))
            base_path = latest_checkpoint.replace("_actor.pth", "")
            print(f"Resuming training from {base_path} (Episode {latest_episode})")
            model.load(base_path)  # Use the correct base path
        else:
            print("No actor checkpoints found. Starting fresh.")
    elif training_cfg.overwrite:
        print("Overwriting existing checkpoints. Starting fresh.")

    return latest_episode


def plot_metrics(rewards, critic1_losses, critic2_losses, metrics_file):
    plt.figure(figsize=(12, 6))

    plt.subplot(2, 1, 1)
    plt.plot(rewards, label="Total Reward")
    plt.xlabel("Episode")
    plt.ylabel("Reward")
    plt.legend()

    plt.subplot(2, 1, 2)
    plt.plot(critic1_losses, label="Critic 1 Loss")
    plt.plot(critic2_losses, label="Critic 2 Loss")
    plt.xlabel("Training Steps")
    plt.ylabel("Loss")
    plt.legend()

    plt.tight_layout()
    plt.savefig(metrics_file)
    print(f"Metrics saved to {metrics_file}")
    plt.show()


if __name__ == "__main__":
    main()
