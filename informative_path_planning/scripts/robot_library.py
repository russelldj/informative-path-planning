# !/usr/bin/python

"""
This library allows access to the simulated robot class, which can be designed using a number of parameters.
"""
import logging
import math
import os
import pdb
import time
from itertools import chain

import dubins
import GPy as GPy
import matplotlib
import numpy as np
import scipy as sp
from IPython.display import display
from matplotlib import cm
from matplotlib import pyplot as plt
from matplotlib.colors import LogNorm
from scipy.stats import multivariate_normal
from sklearn import mixture

logger = logging.getLogger("robot")

import aq_library as aqlib
import envmodel_library as envlib
import evaluation_library as evalib
import gpmodel_library as gplib
import mcts_library as mctslib
import obstacles as obslib
import paths_library as pathlib


class Robot(object):
    """The Robot class, which includes the vehicles current model of the world and IPP algorithms."""

    def __init__(
        self,
        sample_world,
        start_loc=(0.0, 0.0, 0.0),
        extent=(-10.0, 10.0, -10.0, 10.0),
        kernel_file=None,
        kernel_dataset=None,
        prior_dataset=None,
        init_lengthscale=10.0,
        init_variance=100.0,
        noise=0.05,
        path_generator="default",
        frontier_size=6,
        horizon_length=5,
        turning_radius=1,
        sample_step=0.5,
        evaluation=None,
        f_rew="mean",
        create_animation=False,
        learn_params=False,
        nonmyopic=False,
        computation_budget=10,
        rollout_length=5,
        discretization=(10, 10),
        use_cost=False,
        MIN_COLOR=-25.0,
        MAX_COLOR=25.0,
        goal_only=False,
        obstacle_world=obslib.FreeWorld(),
        tree_type="dpw",
    ):
        """Initialize the robot class with a GP model, initial location, path sets, and prior dataset
        Inputs:
            sample_world (method) a function handle that takes a set of locations as input and returns a set of observations
            start_loc (tuple of floats) the location of the robot initially in 2-D space e.g. (0.0, 0.0, 0.0)
            extent (tuple of floats): a tuple representing the max/min of 2D rectangular domain i.e. (-10, 10, -50, 50)
            kernel_file (string) a filename specifying the location of the stored kernel values
            kernel_dataset (tuple of nparrays) a tuple (xvals, zvals), where xvals is a Npoint x 2 nparray of type float and zvals is a Npoint x 1 nparray of type float
            prior_dataset (tuple of nparrays) a tuple (xvals, zvals), where xvals is a Npoint x 2 nparray of type float and zvals is a Npoint x 1 nparray of type float
            init_lengthscale (float) lengthscale param of kernel
            init_variance (float) variance param of kernel
            noise (float) the sensor noise parameter of kernel
            path_generator (string): one of default, dubins, or equal_dubins. Robot path parameterization.
            frontier_size (int): the number of paths in the generated path set
            horizon_length (float): the length of the paths generated by the robot
            turning_radius (float): the turning radius (in units of distance) of the robot
            sample_set (float): the step size (in units of distance) between sequential samples on a trajectory
            evaluation (Evaluation object): an evaluation object for performance metric compuation
            f_rew (string): the reward function. One of {hotspot_info, mean, info_gain, exp_info, mes}
                    create_animation (boolean): save the generate world model and trajectory to file at each timestep
        """

        # Parameterization for the robot
        self.ranges = extent
        self.create_animation = create_animation
        self.eval = evaluation
        self.loc = start_loc
        self.sample_world = sample_world
        self.f_rew = f_rew
        self.fs = frontier_size
        self.discretization = discretization
        self.tree_type = tree_type

        self.maxes = []
        self.current_max = -1000
        self.current_max_loc = [0, 0]
        self.max_locs = None
        self.max_val = None
        self.target = None
        self.noise = noise

        self.learn_params = learn_params
        self.use_cost = use_cost

        if f_rew == "hotspot_info":
            self.aquisition_function = aqlib.hotspot_info_UCB
        elif f_rew == "mean":
            self.aquisition_function = aqlib.mean_UCB
        elif f_rew == "info_gain":
            self.aquisition_function = aqlib.info_gain
        elif f_rew == "mes":
            self.aquisition_function = aqlib.mves
        elif f_rew == "maxs-mes":
            self.aquisition_function = aqlib.mves_maximal_set
        elif f_rew == "exp_improve":
            self.aquisition_function = aqlib.exp_improvement
        elif f_rew == "naive":
            self.aquisition_function = aqlib.naive
            self.sample_num = 3
            self.sample_radius = 1.5
        elif f_rew == "naive_value":
            self.aquisition_function = aqlib.naive_value
            self.sample_num = 3
            self.sample_radius = 3.0
        else:
            raise ValueError(
                "Only 'hotspot_info' and 'mean' and 'info_gain' and 'mes' and 'exp_improve' reward fucntions supported."
            )

        # Initialize the robot's GP model with the initial kernel parameters
        self.GP = gplib.OnlineGPModel(
            ranges=extent,
            lengthscale=init_lengthscale,
            variance=init_variance,
            noise=self.noise,
        )

        # If both a kernel training dataset and a prior dataset are provided, train the kernel using both
        if kernel_dataset is not None and prior_dataset is not None:
            data = np.vstack([prior_dataset[0], kernel_dataset[0]])
            observations = np.vstack([prior_dataset[1], kernel_dataset[1]])
            self.GP.train_kernel(data, observations, kernel_file)
        # Train the kernel using the provided kernel dataset
        elif kernel_dataset is not None:
            self.GP.train_kernel(kernel_dataset[0], kernel_dataset[1], kernel_file)
        # If a kernel file is provided, load the kernel parameters
        elif kernel_file is not None:
            self.GP.load_kernel()
        # No kernel information was provided, so the kernel will be initialized with provided values
        else:
            pass

        # Incorporate the prior dataset into the model
        if prior_dataset is not None:
            self.GP.add_data(prior_dataset[0], prior_dataset[1])

        # The path generation class for the robot
        path_options = {
            "default": pathlib.Path_Generator(
                frontier_size,
                horizon_length,
                turning_radius,
                sample_step,
                self.ranges,
                obstacle_world,
            ),
            "dubins": pathlib.Dubins_Path_Generator(
                frontier_size,
                horizon_length,
                turning_radius,
                sample_step,
                self.ranges,
                obstacle_world,
            ),
            "equal_dubins": pathlib.Dubins_EqualPath_Generator(
                frontier_size,
                horizon_length,
                turning_radius,
                sample_step,
                self.ranges,
                obstacle_world,
            ),
            "fully_reachable_goal": pathlib.Reachable_Frontier_Generator(
                extent,
                discretization,
                sample_step,
                turning_radius,
                horizon_length,
                obstacle_world,
            ),
            "fully_reachable_step": pathlib.Reachable_Step_Generator(
                extent,
                discretization,
                sample_step,
                turning_radius,
                horizon_length,
                obstacle_world,
            ),
        }
        self.path_generator = path_options[path_generator]
        self.path_option = path_generator

        self.nonmyopic = nonmyopic
        self.comp_budget = computation_budget
        self.roll_length = rollout_length

        self.step_size = horizon_length
        self.sample_step = sample_step
        self.turning_radius = turning_radius

        self.MIN_COLOR = MIN_COLOR
        self.MAX_COLOR = MAX_COLOR

        x1vals = np.linspace(extent[0], extent[1], discretization[0])
        x2vals = np.linspace(extent[2], extent[3], discretization[1])
        x1, x2 = np.meshgrid(x1vals, x2vals, sparse=False, indexing="xy")
        self.goals = np.vstack([x1.ravel(), x2.ravel()]).T
        self.goal_only = goal_only

        self.obstacle_world = obstacle_world

    def choose_trajectory(self, t):
        """Select the best trajectory avaliable to the robot at the current pose, according to the aquisition function.
        Input:
            t (int > 0): the current planning iteration (value of a point can change with algortihm progress)
        Output:
            either None or the (best path, best path value, all paths, all values, the max_locs for some functions)
        """
        value = {}
        param = None

        max_locs = max_vals = None
        if self.f_rew == "mes" or self.f_rew == "maxs-mes":
            self.max_val, self.max_locs, self.target = aqlib.sample_max_vals(
                self.GP,
                t=t,
                visualize=True,
                f_rew=self.f_rew,
                obstacles=self.obstacle_world,
            )
        elif self.f_rew == "naive" or self.f_rew == "naive_value":
            param = (self.sample_num, self.sample_radius)
            param = (
                aqlib.sample_max_vals(
                    self.GP,
                    t=t,
                    obstacles=self.obstacle_world,
                    visualize=True,
                    f_rew=self.f_rew,
                    nK=int(self.sample_num),
                ),
                self.sample_radius,
            )
        pred_loc, pred_val = self.predict_max()

        paths, true_paths = self.path_generator.get_path_set(self.loc)

        for path, points in list(paths.items()):
            # set params
            if self.f_rew == "mes" or self.f_rew == "maxs-mes":
                param = (self.max_val, self.max_locs, self.target)
            elif self.f_rew == "exp_improve":
                if len(self.maxes) == 0:
                    param = [self.current_max]
                else:
                    param = self.maxes
            #  get costs
            cost = 100.0
            if self.use_cost == True:
                cost = float(self.path_generator.path_cost(true_paths[path]))
                if cost == 0.0:
                    cost = 100.0

            # set the points over which to determine reward
            if self.path_option == "fully_reachable_goal" and self.goal_only == True:
                poi = [(points[-1][0], points[-1][1])]
            elif self.path_option == "fully_reachable_step" and self.goal_only == True:
                poi = [(self.goals[path][0], self.goals[path][1])]
            else:
                poi = points

            if self.use_cost == False:
                value[path] = self.aquisition_function(
                    time=t, xvals=poi, robot_model=self.GP, param=param
                )
            else:
                reward = self.aquisition_function(
                    time=t, xvals=poi, robot_model=self.GP, param=param
                )
                value[path] = reward / cost
        try:
            best_key = np.random.choice(
                [key for key in list(value.keys()) if value[key] == max(value.values())]
            )
            return (
                paths[best_key],
                true_paths[best_key],
                value[best_key],
                paths,
                value,
                self.max_locs,
            )
        except:
            return None

    def collect_observations(self, xobs):
        """Gather noisy samples of the environment and updates the robot's GP model.
        Input:
            xobs (float array): an nparray of floats representing observation locations, with dimension NUM_PTS x 2
        """
        zobs = self.sample_world(xobs)
        self.GP.add_data(xobs, zobs)

        for z, x in zip(zobs, xobs):
            if z[0] > self.current_max:
                self.current_max = z[0]
                self.current_max_loc = [x[0], x[1]]

    def predict_max(self):
        # If no observations have been collected, return default value
        if self.GP.xvals is None:
            return np.array([0.0, 0.0]), 0.0

        """ First option, return the max value observed so far """
        # return self.GP.xvals[np.argmax(self.GP.zvals), :], np.max(self.GP.zvals)

        """ Second option: generate a set of predictions from model and return max """
        # Generate a set of observations from robot model with which to predict mean
        x1vals = np.linspace(self.ranges[0], self.ranges[1], 30)
        x2vals = np.linspace(self.ranges[2], self.ranges[3], 30)
        x1, x2 = np.meshgrid(x1vals, x2vals, sparse=False, indexing="xy")
        data = np.vstack([x1.ravel(), x2.ravel()]).T
        observations, var = self.GP.predict_value(data)

        return data[np.argmax(observations), :], np.max(observations)

    def planner(self, T):
        """Gather noisy samples of the environment and updates the robot's GP model
        Input:
            T (int > 0): the length of the planning horization (number of planning iterations)
        """
        self.trajectory = []
        self.dist = 0

        for t in range(T):
            # Select the best trajectory according to the robot's aquisition function
            print("[", t, "] Current Location:  ", self.loc)
            logger.info("[{}] Current Location: {}".format(t, self.loc))

            # Let's figure out where the best point is in our world
            pred_loc, pred_val = self.predict_max()
            print("Current predicted max and value: \t", pred_loc, "\t", pred_val)
            logger.info(
                "Current predicted max and value: {} \t {}".format(pred_loc, pred_val)
            )

            if self.nonmyopic == False:
                (
                    sampling_path,
                    best_path,
                    best_val,
                    all_paths,
                    all_values,
                    max_locs,
                ) = self.choose_trajectory(t=t)
            else:
                # set params
                if self.f_rew == "exp_improve":
                    param = self.current_max
                elif self.f_rew == "naive" or self.f_rew == "naive_value":
                    param = (self.sample_num, self.sample_radius)
                else:
                    param = None
                # create the tree search
                mcts = mctslib.cMCTS(
                    self.comp_budget,
                    self.GP,
                    self.loc,
                    self.roll_length,
                    self.path_generator,
                    self.aquisition_function,
                    self.f_rew,
                    t,
                    aq_param=param,
                    use_cost=self.use_cost,
                    tree_type=self.tree_type,
                )
                (
                    sampling_path,
                    best_path,
                    best_val,
                    all_paths,
                    all_values,
                    self.max_locs,
                    self.max_val,
                ) = mcts.choose_trajectory(t=t)

            # Update eval metrics
            start = self.loc
            for m in best_path:
                self.dist += np.sqrt((start[0] - m[0]) ** 2 + (start[1] - m[1]) ** 2)
                start = m
            self.eval.update_metrics(
                len(self.trajectory),
                self.GP,
                all_paths,
                sampling_path,
                value=best_val,
                max_loc=pred_loc,
                max_val=pred_val,
                params=[
                    self.current_max,
                    self.current_max_loc,
                    self.max_val,
                    self.max_locs,
                ],
                dist=self.dist,
            )

            if best_path == None:
                break
            data = np.array(sampling_path)
            x1 = data[:, 0]
            x2 = data[:, 1]
            xlocs = np.vstack([x1, x2]).T

            self.collect_observations(xlocs)
            if t < T / 3 and self.learn_params == True:
                self.GP.train_kernel()
            self.trajectory.append(best_path)

            if self.create_animation:
                print("Creating Visualization")
                self.visualize_trajectory(
                    screen=False,
                    filename=t,
                    best_path=sampling_path,
                    maxes=self.max_locs,
                    all_paths=all_paths,
                    all_vals=all_values,
                )

            # if t > 50:
            #    self.visualize_reward(screen = True, filename = 'REWARD_' + str(t), t = t)

            self.loc = sampling_path[-1]
        np.savetxt(
            "./naive_figures/" + self.f_rew + "/robot_model.csv",
            (self.GP.xvals[:, 0], self.GP.xvals[:, 1], self.GP.zvals[:, 0]),
        )

    def visualize_trajectory(
        self,
        screen=True,
        filename="SUMMARY",
        best_path=None,
        maxes=None,
        all_paths=None,
        all_vals=None,
    ):
        """Visualize the set of paths chosen by the robot
        Inputs:
            screen (boolean): determines whether the figure is plotted to the screen or saved to file
            filename (string): substring for the last part of the filename i.e. '0', '1', ...
            best_path (path object)
            maxes (list of locations)
            all_paths (list of path objects)
            all_vals (list of all path rewards)
            T (string or int): string append to the figure filename
        """

        # Generate a set of observations from robot model with which to make contour plots
        x1vals = np.linspace(self.ranges[0], self.ranges[1], 100)
        x2vals = np.linspace(self.ranges[2], self.ranges[3], 100)
        x1, x2 = np.meshgrid(x1vals, x2vals, sparse=False, indexing="xy")
        data = np.vstack([x1.ravel(), x2.ravel()]).T
        observations, var = self.GP.predict_value(data)

        # Plot the current robot model of the world
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.set_xlim(self.ranges[0:2])
        ax.set_ylim(self.ranges[2:])
        plot = ax.contourf(
            x1,
            x2,
            observations.reshape(x1.shape),
            cmap="viridis",
            vmin=self.MIN_COLOR,
            vmax=self.MAX_COLOR,
            levels=np.linspace(self.MIN_COLOR, self.MAX_COLOR, 15),
        )
        if self.GP.xvals is not None:
            scatter = ax.scatter(
                self.GP.xvals[:, 0], self.GP.xvals[:, 1], c="k", s=20.0, cmap="viridis"
            )
        color = iter(plt.cm.cool(np.linspace(0, 1, len(self.trajectory))))

        # Plot the current trajectory
        for i, path in enumerate(self.trajectory):
            c = next(color)
            f = np.array(path)
            plt.plot(f[:, 0], f[:, 1], c=c)

        # If available, plot the current set of options available to robot, colored
        # by their value (red: low, yellow: high)
        if all_paths is not None:
            all_vals = [x for x in list(all_vals.values())]
            path_color = iter(
                plt.cm.autumn(
                    np.linspace(0, max(all_vals), len(all_vals)) / max(all_vals)
                )
            )
            path_order = np.argsort(all_vals)

            for index in path_order:
                c = next(path_color)
                points = all_paths[list(all_paths.keys())[index]]
                f = np.array(points)
                plt.plot(f[:, 0], f[:, 1], c=c)

        # If available, plot the selected path in green
        if best_path is not None:
            f = np.array(best_path)
            plt.plot(f[:, 0], f[:, 1], c="g")

        # If available, plot the current location of the maxes for mes
        if maxes is not None:
            for coord in maxes:
                plt.scatter(coord[0], coord[1], color="r", marker="*", s=500.0)
            # plt.scatter(maxes[:, 0], maxes[:, 1], color = 'r', marker = '*', s = 500.0)

        # If available, plot the obstacles in the world
        if len(self.obstacle_world.get_obstacles()) != 0:
            for o in self.obstacle_world.get_obstacles():
                x, y = o.exterior.xy
                plt.plot(x, y, "r", linewidth=3)

        # Either plot to screen or save to file
        if screen:
            plt.show()
        else:
            if not os.path.exists("./figures/" + str(self.f_rew)):
                os.makedirs("./figures/" + str(self.f_rew))
            fig.savefig(
                "./figures/"
                + str(self.f_rew)
                + "/trajectory-N."
                + str(filename)
                + ".png"
            )
            # plt.show()
            plt.close()

    def visualize_reward(self, screen=True, filename="REWARD", t=0):
        # Generate a set of observations from robot model with which to make contour plots
        x1vals = np.linspace(self.ranges[0], self.ranges[1], 100)
        x2vals = np.linspace(self.ranges[2], self.ranges[3], 100)
        x1, x2 = np.meshgrid(
            x1vals, x2vals, sparse=False, indexing="xy"
        )  # dimension: NUM_PTS x NUM_PTS
        data = np.vstack([x1.ravel(), x2.ravel()]).T

        if self.f_rew == "mes" or self.f_rew == "maxs-mes":
            param = (self.max_val, self.max_locs, self.target)
        elif self.f_rew == "exp_improve":
            if len(self.maxes) == 0:
                param = [self.current_max]
            else:
                param = self.maxes
        else:
            param = None

        """
        r = self.aquisition_function(time = t, xvals = data, robot_model = self.GP, param = param)
        print "rewrd:", r
        print "Shape reward:", r.shape
        """

        reward = []
        for x in data:
            x = x.reshape((1, 2))
            r = self.aquisition_function(
                time=t, xvals=x, robot_model=self.GP, param=param
            )
            reward.append(r)
        reward = np.array(reward)

        fig2, ax2 = plt.subplots(figsize=(8, 6))
        ax2.set_xlim(self.ranges[0:2])
        ax2.set_ylim(self.ranges[2:])
        ax2.set_title("Reward Plot of the Robot's World Model")
        # plot = ax2.contourf(x1, x2, reward.reshape(x1.shape), cmap = 'viridis', vmin = self.MIN_COLOR, vmax = self.MAX_COLOR, levels=np.linspace(self.MIN_COLOR, self.MAX_COLOR, 15))
        plot = ax2.contourf(x1, x2, reward.reshape(x1.shape), cmap="viridis")

        # Plot the samples taken by the robot
        if self.GP.xvals is not None:
            scatter = ax2.scatter(
                self.GP.xvals[:, 0],
                self.GP.xvals[:, 1],
                c=self.GP.zvals.ravel(),
                s=10.0,
                cmap="viridis",
            )
        if screen:
            plt.show()
        else:
            if not os.path.exists("./figures/" + str(self.f_rew)):
                os.makedirs("./figures/" + str(self.f_rew))
            fig.savefig(
                "./figures/"
                + str(self.f_rew)
                + "/world_model."
                + str(filename)
                + ".png"
            )
            plt.close()

    def visualize_world_model(self, screen=True, filename="SUMMARY"):
        """Visaulize the robots current world model by sampling points uniformly in space and
        plotting the predicted function value at those locations.
        Inputs:
            screen (boolean): determines whether the figure is plotted to the screen or saved to file
            filename (String): name of the file to be made
            maxes (locations of largest points in the world)
        """
        # Generate a set of observations from robot model with which to make contour plots
        x1vals = np.linspace(self.ranges[0], self.ranges[1], 100)
        x2vals = np.linspace(self.ranges[2], self.ranges[3], 100)
        x1, x2 = np.meshgrid(
            x1vals, x2vals, sparse=False, indexing="xy"
        )  # dimension: NUM_PTS x NUM_PTS
        data = np.vstack([x1.ravel(), x2.ravel()]).T
        observations, var = self.GP.predict_value(data)

        fig2, ax2 = plt.subplots(figsize=(8, 6))
        ax2.set_xlim(self.ranges[0:2])
        ax2.set_ylim(self.ranges[2:])
        ax2.set_title("Countour Plot of the Robot's World Model")
        plot = ax2.contourf(
            x1,
            x2,
            observations.reshape(x1.shape),
            cmap="viridis",
            vmin=self.MIN_COLOR,
            vmax=self.MAX_COLOR,
            levels=np.linspace(self.MIN_COLOR, self.MAX_COLOR, 15),
        )

        # Plot the samples taken by the robot
        if self.GP.xvals is not None:
            scatter = ax2.scatter(
                self.GP.xvals[:, 0],
                self.GP.xvals[:, 1],
                c=self.GP.zvals.ravel(),
                s=10.0,
                cmap="viridis",
            )
        if screen:
            plt.show()
        else:
            if not os.path.exists("./figures/" + str(self.f_rew)):
                os.makedirs("./figures/" + str(self.f_rew))
            fig.savefig(
                "./figures/"
                + str(self.f_rew)
                + "/world_model."
                + str(filename)
                + ".png"
            )
            plt.close()

    def plot_information(self):
        """Visualizes the accumulation of reward and aquisition functions"""
        self.eval.plot_metrics()
