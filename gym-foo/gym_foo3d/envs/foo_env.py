import wx
import sys
import pydart2 as pydart
import numpy as np
import cMat
import SimbiconController_3d as SC
import math
import queue
#import Cgui

from guiModule import ModuleTest_drawMesh_new
from wx import glcanvas

from OpenGL.GL import *
from OpenGL.GLUT import *
from OpenGL.GLU import *

import gym
from gym import error, spaces, utils
from gym.utils import seeding

import threading
import time

import matplotlib
import matplotlib.pyplot as plt

from . import env_base

skel_path="/home/qfei/dart/data/sdf/atlas/"
class FooEnv(env_base.FooEnvBase):
    def init_sim(self):
        super().init_sim()
        self.action_space = spaces.Box(low = 0, high = 1.5, shape=(14,))


    def step(self, action):
        pos_before = self.sim.skeletons[1].com()
        panelty = 0
        check = 0
        action = self.clip_Scaling_Actiond10(action)

        self.do_simulation(action,self.frameskip)
        
        #발의 위치
        r_foot_pos = self._getJointPosition(self.r_foot) 
        l_foot_pos = self._getJointPosition(self.l_foot)

        pos_after = self.sim.skeletons[1].com()
        self.XveloQueue.enqueue(pos_after[0])
        self.ZveloQueue.enqueue(pos_after[2])
        
        #2초간의 속도 계산
        #velocity_2s = np.sqrt(np.square(self.XveloQueue.first_end_distance())+np.square(self.ZveloQueue.first_end_distance()))
        velocity_2s = np.sqrt(self.XveloQueue.first_end_distance_square() + self.ZveloQueue.first_end_distance_square())/self.XveloQueue.returnSecond(30)
        velocityReward = np.abs(velocity_2s - self.desiredSpeed)

        ##직선 보행 panelty
        y_lane = np.abs(pos_after[2])

        alive_bonus = 2.5
        #reward = alive_bonus - velocityReward - y_lane * 0.2 - 3*np.abs(self.getCOMFrameXAxis()[2])
        reward = alive_bonus - velocityReward - 4*np.abs(self.getCOMFrameXAxis()[2])
        
        #reward = alive_bonus - velocityReward*0.9 -y_lane*0.2 - (np.abs(self.skel.q[0] + np.pi*0.5) + np.abs(self.skel.q[1]) + np.abs(self.skel.q[2]))*0.2 - foot_balance
        #reward = alive_bonus - speed[0]*0.7 -np.abs(pos_after[2])*0.1 - (anglesPanelty + np.abs(self.skel.q[0] + np.pi*0.5) + np.abs(self.skel.q[1]) + np.abs(self.skel.q[2]))*0.5 
        #reward = alive_bonus - panelty * 0.2 - anglesPanelty

        if pos_after[1] < 0.025 or pos_after[1] > 0.5:
            done = True
        elif np.abs(pos_after[2]) > 2:
            done = True
        elif r_foot_pos[1] > pos_after[1]:
            done = True
        elif l_foot_pos[1] > pos_after[1]:
            done = True
        elif self.step_counter > self.step_per_sec * 60:
            #print("step_counter over")
            done = True
            #reward = reward + 1000 + 0.3*self.step_counter
        elif pos_after[0] < -1:
            print("back ward")
            done = True
        else:
            done = False
        self.step_counter += self.frameskip
        thisState = self.get_state()
        thispos = pos_after[0]
       
        self.actionSteps += 1
        self.episodeTotalReward += reward
        self.set_desiredSpeed()
        if done is True:
            print("episodeDone... mean Reward: " + str(self.episodeTotalReward/self.actionSteps))
            print("velocityReward: " + str(velocityReward) + "__" + str(velocity_2s)+ "__" + str(self.desiredSpeed))
            self.reset()
        return thisState, reward, done, pos_after

        #self.do_simulation(action, 60)



    def do_simulation(self, action, n_frames):
        self.controller.mCurrentStateMachine.mCurrentAction = action
        self.controller.mCurrentStateMachine.setTrainedDesiredAction(action, 0)
        for _ in range(n_frames):
            self.controller.update()
            self.sim.step()
            if(self.isrender):
                time.sleep(0.001)
        return

