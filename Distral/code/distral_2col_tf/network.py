import math
import numpy as np
import random
from memory_replay import Transition
from itertools import count
from torch.distributions import Categorical
import tensorflow as tf


# choose action according to pi_1~pi_i
def select_action(state, policy, model, num_actions,
                  EPS_START, EPS_END, EPS_DECAY, steps_done, alpha, beta):
    """
    Selects whether the next action is choosen by our model or randomly
    """
    # sample = random.random()
    # eps_threshold = EPS_END + (EPS_START - EPS_END) * \
    #     math.exp(-1. * steps_done / EPS_DECAY)
    # .data.max(1)[1].view(1, 1)
    # if sample <= eps_threshold:
    #     return LongTensor([[random.randrange(num_actions)]])

    # print("state = ", state)
    # print("forward = ", model(Variable(state, volatile=True)))
    # Q
    Q = model(Variable(state, volatile=True).type(FloatTensor))
    # pi_0
    pi0 = policy(Variable(state, volatile=True).type(FloatTensor))
    # V
    V = torch.log((torch.pow(pi0, alpha) * torch.exp(beta * Q)).sum(1)) / beta
    # print("pi0 = ", pi0)
    # print(torch.pow(pi0, alpha) * torch.exp(beta * Q))
    # print("V = ", V)
    # use equation 2 to gen pi_i
    pi_i = torch.pow(pi0, alpha) * torch.exp(beta * (Q - V))
    if sum(pi_i.data.numpy()[0] < 0) > 0:
        print("Warning!!!: pi_i has negative values: pi_i", pi_i.data.numpy()[0])
    pi_i = torch.max(torch.zeros_like(pi_i) + 1e-15, pi_i)
    # probabilities = pi_i.data.numpy()[0]
    # print("pi_i = ", pi_i)
    # sample action
    m = Categorical(pi_i)
    action = m.sample().data.view(1, 1)
    return action
    # numpy.random.choice(numpy.arange(0, num_actions), p=probabilities)


# optimize pi_0
def optimize_policy(policy, optimizer, memories, batch_size,
                    num_envs, gamma):
    loss = 0
    for i_env in range(num_envs):
        size_to_sample = np.minimum(batch_size, len(memories[i_env]))
        transitions = memories[i_env].policy_sample(size_to_sample)
        batch = Transition(*zip(*transitions))

        state_batch = Variable(torch.cat(batch.state))
        # print(batch.action)
        time_batch = Variable(torch.cat(batch.time))
        actions = np.array([action.numpy()[0][0] for action in batch.action])

        cur_loss = (torch.pow(Variable(Tensor([gamma])), time_batch) *
                    torch.log(policy(state_batch)[:, actions])).sum()
        loss -= cur_loss
        # loss = cur_loss if i_env == 0 else loss + cur_loss

    optimizer.zero_grad()
    loss.backward()

    for param in policy.parameters():
        param.grad.data.clamp_(-500, 500)
        # print("policy:", param.grad.data)
    optimizer.step()


# optimize pi_1~pi_i
def optimize_model(policy, model, optimizer, memory, batch_size,
                   alpha, beta, gamma):
    if len(memory) < batch_size:
        return
    transitions = memory.sample(batch_size)
    # Transpose the batch (see http://stackoverflow.com/a/19343/3343043 for
    # detailed explanation).
    batch = Transition(*zip(*transitions))

    # Compute a mask of non-final states and concatenate the batch elements
    non_final_mask = ByteTensor(tuple(map(lambda s: s is not None,
                                          batch.next_state)))
    # We don't want to backprop through the expected action values and volatile
    # will save us on temporarily changing the model parameters'
    # requires_grad to False!
    non_final_next_states = Variable(torch.cat([s for s in batch.next_state
                                                if s is not None]),
                                     volatile=True)

    state_batch = Variable(torch.cat(batch.state))
    action_batch = Variable(torch.cat(batch.action))
    reward_batch = Variable(torch.cat(batch.reward))

    # Compute Q(s_t, a) - the model computes Q(s_t), then we select the
    # columns of actions taken
    state_action_values = model(state_batch).gather(1, action_batch)

    # Compute V(s_{t+1}) for all next states.
    next_state_values = Variable(torch.zeros(batch_size).type(Tensor))
    next_state_values[non_final_mask] = torch.log(
        (torch.pow(policy(non_final_next_states), alpha)
         * torch.exp(beta * model(non_final_next_states))).sum(1)) / beta
    # Now, we don't want to mess up the loss with a volatile flag, so let's
    # clear it. After this, we'll just end up with a Variable that has
    # requires_grad=False
    next_state_values.volatile = False
    # Compute the expected Q values
    expected_state_action_values = (next_state_values * gamma) + reward_batch

    # Compute Huber loss
    loss = F.mse_loss(state_action_values + 1e-16, expected_state_action_values)
    # print("loss:", loss)
    # Optimize the model
    optimizer.zero_grad()
    loss.backward()
    for param in model.parameters():
        param.grad.data.clamp_(-500, 500)
        # print("model:", param.grad.data)
    optimizer.step()