#/usr/bin/env python
from hpp.corbaserver.manipulation.robot import Robot
from hpp.corbaserver.manipulation import newProblem, ProblemSolver, ConstraintGraph, Rule
from hpp.gepetto.manipulation import ViewerFactory
from hpp import Transform
import CORBA, sys, numpy as np

newProblem()

Robot.packageName = "talos_data"
Robot.urdfName = "talos"
# Robot.urdfSuffix = '_full'
Robot.urdfSuffix = '_full_accurate_gripper'
Robot.srdfSuffix= ''

class Box (object):
  rootJointType = 'freeflyer'
  packageName = 'gerard_bauzil'
  urdfName = 'cardboard_box'
  urdfSuffix = ""
  srdfSuffix = ""
  handles = [ "box/handle1", "box/handle2" ]
  contacts = [ "box/bottom_surface", ]

class Table (object):
  rootJointType = 'anchor'
  packageName = 'gerard_bauzil'
  urdfName = 'pedestal_table'
  urdfSuffix = ""
  srdfSuffix = ""
  pose = "pose"
  contacts = [ "table/support", ]

Object = Box
half_sitting = [
        # -0.74,0,1.0192720229567027,0,0,0,1, # root_joint
        -0.6,-0.2,1.0192720229567027,0,0,0,1, # root_joint
        0.0, 0.0, -0.411354, 0.859395, -0.448041, -0.001708, # leg_left
        0.0, 0.0, -0.411354, 0.859395, -0.448041, -0.001708, # leg_right
        0, 0.006761, # torso
        0.25847, 0.173046, -0.0002, -0.525366, 0, 0, 0.1, # arm_left
        0, 0, 0, 0, 0, 0, 0, # gripper_left
        -0.25847, -0.173046, 0.0002, -0.525366, 0, 0, 0.1, # arm_right
        0, 0, 0, 0, 0, 0, 0, # gripper_right
        0, 0, # head

        -0.04,0,1.095+0.071,0,0,1,0, # box
        ]

def makeRobotProblemAndViewerFactory ():
    robot = Robot ('dev', 'talos', rootJointType = "freeflyer")
    robot. leftAnkle = "talos/leg_left_6_joint"
    robot.rightAnkle = "talos/leg_right_6_joint"

    robot.setJointBounds ("talos/root_joint", [-1, 1, -1, 1, 0.5, 1.5])

    ps = ProblemSolver (robot)
    ps.setRandomSeed(123)
    ps.selectPathProjector("Progressive", 0.2)
    ps.setErrorThreshold (1e-3)
    ps.setMaxIterProjection (40)

    ps.addPathOptimizer("SimpleTimeParameterization")

    vf = ViewerFactory (ps)
    vf.loadObjectModel (Object, 'box')
    robot.setJointBounds ("box/root_joint", [-1, 1, -1, 1, 0, 2])

    # Loaded as an object to get the visual tags at the right position.
    # vf.loadEnvironmentModel (Table, 'table')
    vf.loadObjectModel (Table, 'table')

    return robot, ps, vf

def makeGraph (robot):
    graph = ConstraintGraph.buildGenericGraph(robot, 'graph',
            # [ "talos/left_gripper", "talos/right_gripper", "table/pose", ],
            [ "talos/left_gripper", ],
            [ "box", ],
            [ Object.handles, ],
            [ Object.contacts, ],
            # [ [], ],
            Table.contacts,
            [
              Rule([ "talos/left_gripper", ], [ Object.handles[1], ], False),
              # Rule([ "talos/left_gripper", ], [ Object.handles[0], ], True),
              Rule([ "talos/left_gripper", ], [ ".*", ], True),
              # Rule([ "talos/right_gripper", ], [ Object.handles[1], ], True),
              ]
            )
    return graph

robot, ps, vf = makeRobotProblemAndViewerFactory()

q_init = robot.getCurrentConfig()

ps.addPartialCom ("talos", ["talos/root_joint"])
ps.addPartialCom ("talos_box", ["talos/root_joint", "box/root_joint"])

ps.createStaticStabilityConstraints ("balance", half_sitting, "talos", ProblemSolver.FIXED_ON_THE_GROUND)
foot_placement = [ "balance/pose-left-foot", "balance/pose-right-foot" ]
foot_placement_complement = [ ]

robot.setCurrentConfig(half_sitting)
com_wf = np.array(ps.getPartialCom("talos"))
tf_la = Transform (robot.getJointPosition(robot.leftAnkle))
com_la = tf_la.inverse().transform(com_wf)

ps.createRelativeComConstraint ("com_talos_box", "talos_box", robot.leftAnkle, com_la.tolist(), (True, True, True))
ps.createRelativeComConstraint ("com_talos"    , "talos"    , robot.leftAnkle, com_la.tolist(), (True, True, True))

ps.createPositionConstraint ("gaze", "talos/rgbd_optical_joint", "box/root_joint", (0,0,0), (0,0,0), (True, True, False))

left_gripper_lock = []
right_gripper_lock = []
other_lock = ["talos/torso_1_joint"]
for n in robot.jointNames:
    s = robot.getJointConfigSize(n)
    r = robot.rankInConfiguration[n]
    if n.startswith ("talos/gripper_right"):
        ps.createLockedJoint(n, n, half_sitting[r:r+s])
        right_gripper_lock.append(n)
    elif n.startswith ("talos/gripper_left"):
        ps.createLockedJoint(n, n, half_sitting[r:r+s])
        left_gripper_lock.append(n)
    elif n in other_lock:
        ps.createLockedJoint(n, n, half_sitting[r:r+s])

graph = makeGraph (robot)

graph.setConstraints (graph=True,
        lockDof = left_gripper_lock + right_gripper_lock + other_lock,
        numConstraints = [ "com_talos_box", "gaze"] + foot_placement)
graph.initialize()

# res, q_init, err = graph.applyNodeConstraints("free", half_sitting)
res, q_init, err = graph.generateTargetConfig("Loop | f", half_sitting, half_sitting)
res, q_init, err = graph.applyNodeConstraints("free", q_init)
# res, q_goal, err = graph.generateTargetConfig("Loop | f", q_tmp, q_tmp)
res, q_goal, err = graph.generateTargetConfig("talos/left_gripper > box/handle1 | f_23", q_init, q_init)
# res, q_goal, err = graph.applyNodeConstraints("talos/right_gripper grasps box/bottom", half_sitting)
# print ps.directPath(q_init, q_init, True)
ps.setInitialConfig(q_init)
# ps.addGoalConfig(q_goal)
ps.setTargetState (graph.nodes["talos/left_gripper grasps box/handle1"])
ps.setParameter("SimpleTimeParameterization/safety", 0.5)
ps.setParameter("SimpleTimeParameterization/order", 2)
ps.setParameter("SimpleTimeParameterization/maxAcceleration", 2.)

ps.setParameter ("ConfigurationShooter/Gaussian/standardDeviation", 0.05)
ps.client.basic.problem.selectConfigurationShooter ("Gaussian")
robot.setCurrentConfig(q_init)
# ps.setRandomSeed(1)
# sys.exit(1)
print ps.solve()

ps.client.manipulation.problem.selectProblem ("estimation")
newProblem()

robotEst, psEst, vfEst = makeRobotProblemAndViewerFactory ()

graphEst = makeGraph (robotEst)
graphEst.initialize()

psEst.setParameter("SimpleTimeParameterization/safety", CORBA.Any(CORBA.TC_double, 0.5))
psEst.setParameter("SimpleTimeParameterization/order", 2)

ps.client.manipulation.problem.selectProblem ("default")
