import time
import math
import gym
import gym_foo
import gym
import torch
import torch.nn as nn
import ptan
import numpy as np
import torch.optim as optim
import torch.nn.functional as F
import gym.spaces
#from tensorboardX import SummaryWriter
HID_SIZE = 128
ENV_ID = "foo-v0"

class ModelA2C(nn.Module) :
    def __init__(self, obs_size, act_size) :
        super(ModelA2C, self).__init__()

        self.base = nn.Sequential(
                nn.Linear(obs_size, HID_SIZE),
                nn.ReLU(),
        )
        
        #mean value of action...(tanh << return range -1...1)
        self.mu = nn.Sequential(
                nn.Linear(HID_SIZE, act_size),
                nn.Tanh(),
        )

        #variance of action...(softplus << smooth ReLU Function)
        self.var = nn.Sequential(
                nn.Linear(HID_SIZE, act_size),
                nn.Softplus(),
        )

        #has no activation function applied
        self.value = nn.Linear(HID_SIZE, 1)


    def forward(self, x):
        base_out = self.base(x)
        return self.mu(base_out), self.var(base_out), self.value(base_out)


class AgentA2C(ptan.agent.BaseAgent):
    def __init__(self, net, device="cuda"):
        self.net = net
        self.device = device

    def __call__(self, states, agent_states):
        states_v = ptan.agent.float32_preprocessor(states).to(device)
        mu_v, var_v, _ = self.net(states_v)
        mu = mu_v.data.cpu().numpy()
        sigma = torch.sqrt(var_v).data.cpu().numpy()

        #return action value using normal distribution
        actions = np.random.normal(mu, sigma)
        actions = np.clip(actions, -1, 1)

        return actions, agent_states


def test_net(net, env, count=10, device="cuda"):
    rewards = 0.0
    steps = 0
    for _ in range (count):
        obs = env.reset()
        print("reset!")
        while True:
            obs_v = ptan.agent.float32_preprocessor([obs]).to(device)
            mu_v = net(obs_v)[0]
            action = mu_v.squeeze(dim=0).data.cpu().numpy()
            #print(action)
            obs, reward, done, _ = env.step(action)
            rewards += reward
            steps += 1
            if done:
                break
    return rewards / count, steps/count

def calc_logprob(mu_v, var_v, action_v):
    p1 = - ((mu_v - action_v) ** 2) / (2*var_v.clamp(min=1e-3))
    p2 = - torch.log(torch.sqrt(2*math.pi * var_v))
    return p1 + p2


def unpack_batch_a2c(batch, net, last_val_gamma , device = "cuda"):
    """
    convert batch into training tensors
    :param batch:
    :param net:
    :return: states variable, actions tensor, reference value variable
    """
    states = []
    actions = []
    rewards = []
    not_done_idx = []
    last_states = []
    for idx, exp in enumerate(batch):
        states.append(exp.state)
        actions.append(exp.action)
        rewards.append(exp.reward)
        if exp.last_state is not None:
            not_done_idx.append(idx)
            last_states.append(exp.last_state)
    states_v = ptan.agent.float32_preprocessor(states).to(device)
    actions_v = torch.FloatTensor(actions).to(device)

    #handle rewards
    rewards_np = np.array(rewards, dtype=np.float32)
    if not_done_idx:
        last_states_v = ptan.agent.float32_preprocessor(last_states).to(device)
        last_vals_v = net(last_states_v)[2]
        last_vals_np = last_vals_v.data.cpu().numpy()[:, 0]
        rewards_np[not_done_idx] += last_val_gamma * last_vals_np

    ref_vals_v = torch.FloatTensor(rewards_np).to(device)
    return states_v, actions_v, ref_vals_v


GAMMA = 0.99
REWARD_STEPS = 2
BATCH_SIZE = 32
LEARNING_RATE = 5e-5
ENTROPY_BETA = 1e-4

TEST_ITERS = 5000

usingPlot = 0
if __name__ == "__main__":
    device = torch.device("cuda")
    env = gym.make(ENV_ID)
    test_env = gym.make(ENV_ID)
    env.init_dart()
    env.init_sim()
    #env.set_env_name("env")
    test_env.init_sim()
    #test_env.set_env_name("test_env")
    #test_env.start_render()
    #env.start_render()
    #print(len(env.observation_space.sample()),len(env.action_space.sample()))

    network = ModelA2C(env.observation_space.shape[0],env.action_space.shape[0]).to(device)
    print(network)
   
    #what is it// Check
    #writer = SummaryWriter(comment="-a2c_")
    #actions, agent_states = test_net(network, env)
    agent = AgentA2C(network, device = device)

    exp_source = ptan.experience.ExperienceSourceFirstLast(env, agent, GAMMA, steps_count=REWARD_STEPS)
    optimizer = optim.Adam(network.parameters(), lr=5e-5)

    batch = []
    best_reward = None
    #with ptan.common.utils.RewardTracker(writer) as tracker:
    for step_idx, exp in enumerate(exp_source):
        #print(exp_source.pop_rewards_steps())
        #input("h")
        rewards_steps = exp_source.pop_rewards_steps()
        #print("rewards_steps",rewards_steps)
        if rewards_steps:
            reward, steps = zip(*rewards_steps)
            #print("in reward steps",reward)
            #print("and",steps)
            #tb_tracker.track("episode_steps", steps[0], step_idx)
            #tracker.reward(reward[0], step_idx)
            #env.draw_plot(steps,reward)
        if step_idx % TEST_ITERS == 0:
            print(step_idx)
            ts = time.time()
            print(ts)
            ##run test Enviroment
            rewards, steps = test_net(network, test_env, device=device)
            print("Test done is %.2f sec, reward %.3f, steps %d" % (time.time() - ts, rewards, steps))
            env.draw_plot(usingPlot,rewards)
            usingPlot = usingPlot + 1
            #writer.add_scalar("test_reward", rewards, step_idx)
            #writer.add_scalar("test_steps", steps, step_idx)
            if best_reward is None or best_reward < rewards:
                if best_reward is not None:
                    print("Best reward updated: %.3f -> %.3f" % (best_reward, rewards))
                    #name = "best_%+.3f_%d.dat" % (rewards, step_idx)
                    #fname = os.path.join(save_path, name)
                    #torch.save(net.state_dict(), fname)
                best_reward = rewards

        batch.append(exp)
        #print("exp", exp)
        if len(batch) < BATCH_SIZE:
            continue
       
        #commentory in book chpater 14
        states_v, actions_v, vals_ref_v = \
                unpack_batch_a2c(batch, network, last_val_gamma=GAMMA ** REWARD_STEPS, device = device)
        batch.clear()

        optimizer.zero_grad()
        mu_v, var_v, value_v = network(states_v)

        loss_value_v = F.mse_loss(value_v.squeeze(-1), vals_ref_v)


       
        adv_v = vals_ref_v.unsqueeze(dim=-1) - value_v.detach()
        log_prob_v = adv_v * calc_logprob(mu_v, var_v, actions_v)

        loss_policy_v = -log_prob_v.mean()
        entropy_loss_v = ENTROPY_BETA * (-(torch.log(2*math.pi*var_v) + 1)/2).mean()

        loss_v = loss_policy_v + entropy_loss_v + loss_value_v
        loss_v.backward()
        optimizer.step()
        #print("end of step")
        #print("step_idx", step_idx)
        #print("value_v" , value_v)
        #print("value_v" , value_v.shape[0])
        #input()
        #for bat_index, bat_reward in enumerate(value_v):
            #usingPlot = usingPlot+ 1
            #print(bat_index)
            #print(bat_reward[0])
            #env.draw_plot(usingPlot,bat_reward[0].item())
        #env.draw_plot(step_idx, value_v)
        

