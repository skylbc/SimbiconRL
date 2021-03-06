import os
import math
import ptan
import time
import gym
import gym_foo
import argparse
from tensorboardX import SummaryWriter

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F

from baseline_ppo.model import Policy

HID_SIZE = 64
ENTROPY_BETA = 1e-3
VALUE_LOSS_COEF = 0.5
##action = env.action_space

class ModelActor(nn.Module):
    def __init__(self, obs_size, act_size):
        super(ModelActor,self).__init__()

        self.mu = nn.Sequential(
                nn.Linear(obs_size, HID_SIZE),
                nn.ReLU(),
                nn.Linear(HID_SIZE, HID_SIZE),
                nn.ReLU(), 
                nn.Linear(HID_SIZE, act_size),
                nn.Tanh(),
        )
        self.logstd = nn.Parameter(torch.zeros(act_size))
        self.train()
    def forward(self, x):
        return self.mu(x)

class ModelCritic(nn.Module):
    def __init__(self, obs_size):
        super(ModelCritic, self).__init__()

        self.value = nn.Sequential(
                nn.Linear(obs_size, HID_SIZE),
                nn.ReLU(),
                nn.Linear(HID_SIZE, HID_SIZE),
                nn.ReLU(),
                nn.Linear(HID_SIZE, 1),
        )
        self.train()

    def forward(self,x):
        return self.value(x)

class AgentA2C(ptan.agent.BaseAgent):
    def __init__(self,net,device ="cuda"):
        self.net = net
        self.device = device

    def __call__(self, states, agent_states):
        states_v = ptan.agent.float32_preprocessor(states).to(self.device)

        mu_v = self.net(states_v)
        mu = mu_v.data.cpu().numpy()
        #print(mu)
        logstd = self.net.logstd.data.cpu().numpy()

        #print(mu)
        actions = mu + np.exp(logstd) * np.random.normal(size=logstd.shape)
        #print(actions)
        #input()
        actions = np.clip(actions, -1, 1)

        return actions, agent_states


ENV_ID = "foo-v0"
GAMMA = 0.99
GAE_LAMBDA = 0.95

TRAJECTORY_SIZE = 4097
LEARNING_RATE_ACTOR = 1e-5
LEARNING_RATE_CRITIC = 1e-3
PPO_EPS = 0.2
PPO_EPOCHES = 10
PPO_BATCH_SIZE = 256

TEST_ITERS = 100000

def test_net(net, env, count=1, device = "cuda"):
    print("test_net_activate")
    rewards = 0.0
    steps = 0
    for _ in range(count):
        obs = env.reset()
        while True:
            obs_v = ptan.agent.float32_preprocessor([obs]).to(device)
            mu_v = net(obs_v)[0]
            action = mu_v.squeeze(dim=0).data.cpu().numpy()
            #print(mu_v)
            #print(action)
            #for i in action:
            #   if i <= -1 or i >= 1:
            #        input(action)
            #for i in action:
            #    print(i)
            action = np.clip(action, -1, 1)
            obs, reward, done, _ = env.step(action)
            rewards += reward
            steps += env.querystep
            if done:
                break
    return rewards / count, steps / count

def calc_logprob(mu_v, logstd_v, actions_v):
    p1 = - ((mu_v - actions_v) ** 2) / (2 * torch.exp(logstd_v).clamp(min = 1e-3))
    p2 = - torch.log(torch.sqrt(2 * math.pi * torch.exp(logstd_v)))
    return p1 + p2

def calc_adv_ref(trajectory, net_crt, states_v, device="cuda"):
    values_v = net_crt(states_v)
    values = values_v.squeeze().data.cpu().numpy()

    last_gae = 0.0
    result_adv = []
    result_ref = []

    #print(values)
    #print(values)
    #print(trajectory)
    #print(len(values))
    #print(len(trajectory))
    for val, next_val, (exp,) in zip(reversed(values[:-1]), reversed(values[1:]),
                                     reversed(trajectory[:-1])):
        if exp.done:
            delta = exp.reward - val
            last_gae = delta
        else:
            delta = exp.reward + GAMMA * next_val - val
            last_gae = delta + GAMMA * GAE_LAMBDA * last_gae
        result_adv.append(last_gae)
        result_ref.append(last_gae + val)

    adv_v = torch.FloatTensor(list(reversed(result_adv))).to(device)
    ref_v = torch.FloatTensor(list(reversed(result_ref))).to(device)

    return adv_v, ref_v


if __name__ == "__main__":
    #parser = argparse.ArgumentParser()
    device = torch.device("cuda")

    save_path = os.path.join("saves", "ppo-samples")
    os.makedirs(save_path, exist_ok = True)

    env = gym.make(ENV_ID)
    #test_env = gym.make(ENV_ID)
    
    env.init_dart()
    env.init_sim()
    #test_env.init_sim()
    #env.set_env_name("env")
    #test_env.set_env_name("test_env")

    #env.start_render()
    net_act = ModelActor(env.observation_space.shape[0], env.action_space.shape[0]).to(device)
    net_crt = ModelCritic(env.observation_space.shape[0]).to(device)
    print(net_act)
    print(net_crt)

    writer = SummaryWriter(comment="-ppo_Sample")
    agent = AgentA2C(net_act, device = device)
    exp_source = ptan.experience.ExperienceSource(env,agent,steps_count = 1, steps_delta = 1)

    opt_act = optim.Adam(net_act.parameters(), lr = LEARNING_RATE_ACTOR)
    opt_crt = optim.Adam(net_crt.parameters(), lr=LEARNING_RATE_CRITIC)

    trajectory = []
    best_reward = None

    what = 0
    usingPlot = 0
    inter_save = 0
    #tracker = ptan.common.utils.RewardTracker(writer)
    with ptan.common.utils.RewardTracker(writer) as tracker:
        for step_idx, exp in enumerate(exp_source): 
            rewards_steps = exp_source.pop_rewards_steps()
            if rewards_steps:
                rewards, steps = zip(*rewards_steps)
                writer.add_scalar("episode_steps", np.mean(steps), step_idx)
                tracker.reward(np.mean(rewards), step_idx)
                print(rewards, step_idx)
            
             
            if step_idx % TEST_ITERS == 0:
                ts = time.time()
                #rewards, steps = test_net(net_act, test_env, device=device)
                #print("Test done in %.2f sec, reward %.3f, steps %d" % (time.time() - ts, rewards, steps))
                #writer.add_scalar("test_reward", rewards, step_idx)
                #writer.add_scalar("test_step", steps, step_idx)
                
                #testCOde
                #if rewards < 0:
                    #test_env.start_render()

                #env.draw_plot(usingPlot,rewards)
                #usingPlot = usingPlot + 1
                """
                if best_reward is None or  best_reward < rewards:
                    if best_reward is not None:
                        print("Best reward updated: %.3f -> %.3f" % (best_reward, rewards))
                        name = "best_%+.3f_%d.dat" % (rewards, step_idx)
                        fname = os.path.join(save_path, name)
                        torch.save(net_act.state_dict(), fname)
                    best_reward = rewards
                """
                print(inter_save)
                if inter_save % 100000 == 0:
                    name = "inter_saves%d" % (step_idx)
                    fname = os.path.join(save_path, name)
                    torch.save(net_act.state_dict(), fname)
                    inter_save = inter_save % 100000
            
            trajectory.append(exp)

            #save variable
            inter_save += 1

            if len(trajectory) < TRAJECTORY_SIZE:
                continue

            traj_states = [t[0].state for t in trajectory]
            traj_actions = [t[0].action for t in trajectory]
            traj_states_v = torch.FloatTensor(traj_states).to(device)
            traj_actions_v = torch.FloatTensor(traj_actions).to(device)
            traj_adv_v, traj_ref_v = calc_adv_ref(trajectory, net_crt, traj_states_v, device=device)
            mu_v = net_act(traj_states_v)
            old_logprob_v = calc_logprob(mu_v, net_act.logstd, traj_actions_v)

            #normalize advantages
            traj_adv_v = (traj_adv_v - torch.mean(traj_adv_v)) / torch.std(traj_adv_v)

            #drop last entry from the trajectory, an our adv and ref value calculatred without it
            trajectory = trajectory[:-1]
            old_logprob_v = old_logprob_v[:-1].detach()

            sum_loss_value = 0.0
            sum_loss_policy = 0.0
            count_steps = 0

            for epoch in range(PPO_EPOCHES):
                for batch_ofs in range(0, len(trajectory), PPO_BATCH_SIZE):
                    states_v = traj_states_v[batch_ofs:batch_ofs + PPO_BATCH_SIZE]
                    actions_v = traj_actions_v[batch_ofs:batch_ofs + PPO_BATCH_SIZE]
                    batch_adv_v = traj_adv_v[batch_ofs:batch_ofs + PPO_BATCH_SIZE].unsqueeze(-1)
                    batch_ref_v = traj_ref_v[batch_ofs:batch_ofs + PPO_BATCH_SIZE]
                    batch_old_logprob_v = old_logprob_v[batch_ofs:batch_ofs + PPO_BATCH_SIZE]

                    # critic training
                    opt_crt.zero_grad()
                    value_v = net_crt(states_v)
                    loss_value_v = F.mse_loss(value_v.squeeze(-1), batch_ref_v)
                    #print(loss_value_v)
                    #print(value_v.squeeze(-1))
                    #print(batch_ref_v)
                    #input()
                    #loss_value_v.backward(retain_graph=True)
                    loss_value_v.backward()
                    opt_crt.step()

                    # actor training
                    opt_act.zero_grad()
                    #print("states_v", states_v)
                    mu_v = net_act(states_v)
                    #print("mu_v", mu_v)
                    logprob_pi_v = calc_logprob(mu_v, net_act.logstd, actions_v)
                    ratio_v = torch.exp(logprob_pi_v - batch_old_logprob_v)
                    surr_obj_v = batch_adv_v * ratio_v
                    clipped_surr_v = batch_adv_v * torch.clamp(ratio_v, 1.0 - PPO_EPS, 1.0 + PPO_EPS)
                    loss_policy_v = -torch.min(surr_obj_v, clipped_surr_v).mean()
                    #print("clipped_surr_v", clipped_surr_v)
                    #print("loss_policy_v",loss_policy_v)

                    ##VALUE_LOSS
                    ##ENTROPY
                    #entropy_loss_v = ENTROPY_BETA * (-(torch.log(2*math.pi*torch.exp(net_act.logstd)) + 1)/2).mean()

                    loss_policy_v.backward()
                    #loss_value_v2 = F.mse_loss(value_v.squeeze(-1), batch_ref_v) 
                    #(loss_policy_v + VALUE_LOSS_COEF*loss_value_v).backward()

                    opt_act.step()
                    #opt_crt.step()
                    sum_loss_value += loss_value_v.item()
                    sum_loss_policy += loss_policy_v.item()
                    count_steps += env.frameskip
                    #print("done", epoch)

            trajectory.clear()
            writer.add_scalar("advantage", traj_adv_v.mean().item(), step_idx)
            writer.add_scalar("values", traj_ref_v.mean().item(), step_idx)
            writer.add_scalar("loss_policy", sum_loss_policy / count_steps, step_idx)
            writer.add_scalar("loss_value", sum_loss_value/ count_steps, step_idx)
