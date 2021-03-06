from pydart2.gui.glut.window import GLUTWindow
import OpenGL.GL as GL
import OpenGL.GLU as GLU
import OpenGL.GLUT as GLUT
import sys
import numpy as np
import SimbiconController
from pydart2.gui.opengl.scene import OpenGLScene
import SimbiconController as SC

class MyWindow(GLUTWindow):
    def __init__(self, sim, title,controller):
        super().__init__(sim,title)
        self.mImpulseDuration=0
        self.mForce= None
        self.mController = controller
    def idle(self, ):
        if self.sim is None:
            return
        if self.is_simulating:
            #External force world->getskeleton->getbodyNode->addExtforce
            print("mForce",self.mForce)
            if self.mForce is not None:
                self.sim.skeletons[1].body("pelvis").add_ext_force(self.mForce)

            #Internal force mController->update(mWorld->getTime())
            print("getTime",self.sim.time())
            #input()
            self.mController.update()
            #simulate one step
            self.sim.step()

            #for pertubation test
            self.mImpulseDuration-=1
            if self.mImpulseDuration <= 0:
                self.mImpulseDuration = 0
                self.mForce=None
    def keyPressed(self, key, x, y):
        keycode = ord(key)
        key = key.decode('utf-8')

        if keycode == 27:
            GLUT.glutDestroyWindow(self.window)
            sys.exit()
        elif key == ' ':
            self.is_simulating = not self.is_simulating
            self.is_animating = False
            print("Simulating....")
        elif key == 'w':
            self.mForce = np.array([-500.0, 0.0, 0.0])
            self.mImpulseDuration=100
            print("push Backward")
        elif key == 's':
            self.mForce = np.array([500.0, 0.0, 0.0])
            self.mImpulseDuration=100
            print("push Forward")
        elif key == '[' :
            self.frame_index = (self.frame_index + 1)  % self.sim.num_frames()
            print("frame = %d/%d" % (self.frame_index, self.sim.num_frames()))
            self.sim.set_frame(self.frame_index)
        elif key == '1':
            input()
            self.mController.changeStateMachine(self.mController.mStateMachines[0],self.mController.mCurrentStateMachine.mBeginTime + self.mController.mCurrentStateMachine.mElapsedTime)
        elif key == '2':
            self.mController.changeStateMachine(self.mController.mStateMachines[1],self.mController.mCurrentStateMachine.mBeginTime + self.mController.mCurrentStateMachine.mElapsedTime)
        elif key == '3':
            self.mController.changeStateMachine(self.mController.mStateMachines[2],self.mController.mCurrentStateMachine.mBeginTime + self.mController.mCurrentStateMachine.mElapsedTime)
        elif key == '4':
            self.mController.changeStateMachine(self.mController.mStateMachines[3],self.mController.mCurrentStateMachine.mBeginTime + self.mController.mCurrentStateMachine.mElapsedTime)


def launch_MyWindow(sim, controller,title=None, default_camera=None):
    win = MyWindow(sim, title,controller)
    launch_window(sim,win,default_camera)

def launch_window(sim, win, default_camera):
    if default_camera is not None:
        win.scene.set_camera(default_camera)
    win.run()
