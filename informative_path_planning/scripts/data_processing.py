# !/usr/bin/python

import math
import os

import aq_library as aqlib
import gpmodel_library as gplib
import GPy as GPy
import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy as sp
from matplotlib import cm
from matplotlib.colors import LogNorm

plt.rcParams["xtick.labelsize"] = 32
plt.rcParams["ytick.labelsize"] = 32
plt.rcParams["axes.labelsize"] = 40
plt.rcParams["axes.titlesize"] = 40
plt.rcParams["figure.figsize"] = (17, 10)


def make_df(file_names, sample_names, max_vals, column_names):
    d = file_names[0]
    d_samp_file = sample_names[0]
    d_max_vals = max_vals[0]

    data = pd.read_table(d, delimiter=" ", header=None)
    data = data.T

    # If info value hasn't been computed
    if data.shape[1] < len(column_names):
        max_info_value = playback(d, d_samp_file, d_max_vals, column_names[0:-1])
        data[column_names[-1]] = pd.Series(np.array(max_info_value), index=data.index)
        data.columns = column_names
        data[column_names].T.to_csv(
            d, sep=" ", header=False, index=False, index_label=False
        )
        print("Adding max_value_info to ", d)

    elif data.shape[1] > len(column_names):
        data = pd.read_table(d, delimiter=" ", header=None, skipfooter=1)
        data = data.T
        # data[column_names].T.to_csv(d+'.mod', sep=" ", header = False, index = False, index_label = False)
        # print "Writing", d+'.mod'
        data.columns = column_names
    else:
        data.columns = column_names

    for index, m in enumerate(file_names[1:]):
        m_samp_file = sample_names[index + 1]
        m_max_vals = max_vals[index + 1]

        temp_data = pd.read_table(m, delimiter=" ", header=None)
        temp_data = temp_data.T

        # If info value hasn't been computed
        if temp_data.shape[1] < len(column_names):
            print("Adding max_value_info to", m)
            max_info_value = playback(m, m_samp_file, m_max_vals, column_names[0:-1])
            temp_data[column_names[-1]] = pd.Series(
                np.array(max_info_value), index=temp_data.index
            )
            temp_data.columns = column_names
            temp_data[column_names].T.to_csv(
                m, sep=" ", header=False, index=False, index_label=False
            )

        elif temp_data.shape[1] > len(column_names):
            temp_data = pd.read_table(m, delimiter=" ", header=None, skipfooter=1)
            temp_data = temp_data.T
            temp_data.columns = column_names
            # temp_data[column_names].T.to_csv(m+'.mod', sep = " ", header = False, index = False, index_label = False)
            # print "Writing", m+'.mod'
        else:
            temp_data.columns = column_names

        data = data.append(temp_data)

    return data


def make_samples_df(file_names, column_names, max_loc, thresh=1.5):
    prop = []
    d = file_names[0]
    sdata = pd.read_table(d, delimiter=" ", header=None)
    sdata = sdata.T
    sdata.columns = column_names
    sdata.loc[:, "Distance"] = sdata.apply(
        lambda x: np.sqrt(
            (x["x"] - max_loc[0][0]) ** 2 + (x["y"] - max_loc[0][1]) ** 2
        ),
        axis=1,
    )
    prop.append(float(len(sdata[sdata.Distance < thresh])) / len(sdata))
    print(len(file_names), len(max_loc))
    for i, m in enumerate(file_names[1:]):
        temp_data = pd.read_table(m, delimiter=" ", header=None)
        temp_data = temp_data.T
        temp_data.columns = column_names
        temp_data.loc[:, "Distance"] = temp_data.apply(
            lambda x: np.sqrt(
                (x["x"] - max_loc[i + 1][0]) ** 2 + (x["y"] - max_loc[i + 1][1]) ** 2
            ),
            axis=1,
        )
        prop.append(float(len(temp_data[temp_data.Distance < thresh])) / len(temp_data))
        sdata = sdata.append(temp_data)

    return sdata, prop


def print_stats(meandf, mesdf, eidf, columns, end_time=174.0, fname="stats.txt"):
    mean_end = meandf[meandf.time == end_time]
    mes_end = mesdf[mesdf.time == end_time]
    if eidf is not None:
        ei_end = eidf[eidf.time == end_time]

    f = open(fname, "a")

    for e in columns:
        f.write("-------------\n")
        f.write(str(e) + "\n")
        f.write(
            "MEAN:    " + str(mean_end[e].mean()) + ", " + str(mean_end[e].std()) + "\n"
        )
        f.write(
            "MES :    " + str(mes_end[e].mean()) + ", " + str(mes_end[e].std()) + "\n"
        )
        print("-------------")
        print(str(e))
        print("MEAN:    " + str(mean_end[e].mean()) + ", " + str(mean_end[e].std()))
        print("MES :    " + str(mes_end[e].mean()) + ", " + str(mes_end[e].std()))
        if eidf is not None:
            f.write("EI  :    " + str(ei_end[e].mean()) + ", " + str(ei_end[e].std()))
            print(
                "EI  :    " + str(ei_end[e].mean()) + ", " + str(ei_end[e].std() + "\n")
            )
    f.close()


def make_histograms(mean_sdata, mes_sdata, ei_sdata, figname=""):
    # make the aggregate histograms
    if ei_sdata is not None:
        fig, axes = plt.subplots(1, 3, sharey=True)
    else:
        fig, axes = plt.subplots(1, 2, sharey=True)

    axes[0].hist(
        mean_sdata["Distance"].values,
        bins=np.linspace(
            min(mean_sdata["Distance"].values),
            max(mean_sdata["Distance"].values),
            np.floor(
                max(mean_sdata["Distance"].values) - min(mean_sdata["Distance"].values)
            ),
        ),
        color="g",
    )
    axes[0].set_title("UCB")
    axes[1].hist(
        mes_sdata["Distance"].values,
        bins=np.linspace(
            min(mean_sdata["Distance"].values),
            max(mean_sdata["Distance"].values),
            np.floor(
                max(mean_sdata["Distance"].values) - min(mean_sdata["Distance"].values)
            ),
        ),
        color="r",
    )
    axes[1].set_title("PLUMES")
    if ei_sdata is not None:
        axes[2].hist(
            ei_sdata["Distance"].values,
            bins=np.linspace(
                min(mean_sdata["Distance"].values),
                max(mean_sdata["Distance"].values),
                np.floor(
                    max(mean_sdata["Distance"].values)
                    - min(mean_sdata["Distance"].values)
                ),
            ),
            color="b",
        )
        axes[2].set_title("EI")
    axes[1].set_xlabel("Distance ($m$) From Maxima")
    axes[0].set_ylabel("Count")
    plt.savefig(figname + "_agg_samples.png")

    # make the proportional barcharts
    if ei_sdata is not None:
        fig = plt.figure()
        plt.bar(
            np.arange(3),
            [sum(m) / len(m) for m in (mean_prop, mes_prop, ei_prop)],
            yerr=[np.std(m) for m in (mean_prop, mes_prop, ei_prop)],
            color=["g", "r", "b"],
        )
        plt.xticks(np.arange(3), ["UCB", "PLUMES", "EI"])
        plt.ylabel("Proportion of Samples")
        plt.title("Average Proportion of Samples taken within 1.5m of the True Maxima")
        plt.savefig("my_prop_samples")
    else:
        fig = plt.figure()
        plt.bar(
            np.arange(2),
            [sum(m) / len(m) for m in (mean_prop, mes_prop)],
            yerr=[np.std(m) for m in (mean_prop, mes_prop)],
            color=["g", "r"],
        )
        plt.xticks(np.arange(2), ["UCB", "PLUMES"])
        plt.ylabel("Proportion of Samples")
        plt.title("Average Proportion of Samples taken within 1.5m of the True Maxima")
        plt.savefig(figname + "_prop_samples")


def make_plots(
    mean_data,
    mes_data,
    ei_data,
    param,
    title,
    d=20,
    plot_confidence=False,
    save_fig=False,
    lab="Value",
    fname="fig",
):
    # based upon the definition of rate of convergence
    ucb = [0 for m in range(149)]
    mes = [0 for m in range(149)]
    ei = [0 for m in range(149)]

    ucb_v = []
    mes_v = []
    ei_v = []

    for i in range(d - 1):
        sm = []
        sme = []
        se = []
        for j in range(149):
            sm.append((mean_data[mean_data.time == j][param].values[i]))
            sme.append((mes_data[mes_data.time == j][param].values[i]))
            if ei_data is not None:
                se.append((ei_data[ei_data.time == j][param].values[i]))
        ucb = [m + n for m, n in zip(ucb, sm)]
        mes = [m + n for m, n in zip(mes, sme)]
        if ei_data is not None:
            ei = [m + n for m, n in zip(ei, se)]

        ucb_v.append(sm)
        mes_v.append(sme)
        ei_v.append(se)

    vucb = []
    vmes = []
    vei = []
    for i in range(149):
        t1 = []
        t2 = []
        t3 = []
        if ei_data is not None:
            for m, n, o in zip(ucb_v, mes_v, ei_v):
                t1.append(m[i])
                t2.append(n[i])
                t3.append(o[i])
            vucb.append(np.std(t1))
            vmes.append(np.std(t2))
            vei.append(np.std(t3))
        else:
            for m, n in zip(ucb_v, mes_v):
                t1.append(m[i])
                t2.append(n[i])
            vucb.append(np.std(t1))
            vmes.append(np.std(t2))

    fig = plt.figure()
    plt.plot([l / d for l in ucb], "g", label="UCB")
    plt.plot([l / d for l in mes], "r", label="PLUMES")
    if ei_data is not None:
        plt.plot([l / d for l in ei], "b", label="EI")

    if plot_confidence:
        x = [i for i in range(149)]
        y1 = [l / d + m for l, m in zip(ucb, vucb)]
        y2 = [l / d - m for l, m in zip(ucb, vucb)]

        y3 = [l / d + m for l, m in zip(mes, vmes)]
        y4 = [l / d - m for l, m in zip(mes, vmes)]

        if ei_data is not None:
            y5 = [l / d + m for l, m in zip(ei, vei)]
            y6 = [l / d - m for l, m in zip(ei, vei)]

        plt.fill_between(x, y1, y2, color="g", alpha=0.2)
        plt.fill_between(x, y3, y4, color="r", alpha=0.2)
        if ei_data is not None:
            plt.fill_between(x, y5, y6, color="b", alpha=0.2)

    plt.legend(fontsize=30)
    plt.xlabel("Planning Iteration")
    plt.ylabel(lab)

    if save_fig:
        plt.savefig(fname)
    plt.title(title)
    # plt.show()


def playback(playback_locs, playback_samples, max_val, column_names):
    """Gather noisy samples of the environment and updates the robot's GP model
    Input:
        T (int > 0): the length of the planning horization (number of planning iterations)
    """

    d = playback_locs
    data = pd.read_table(d, delimiter=" ", header=None)
    data = data.T
    if data.shape[1] > len(column_names):
        data = pd.read_table(d, delimiter=" ", header=None, skipfooter=2)
        data = data.T
    data.columns = column_names
    robot_loc = np.vstack((data["robot_loc_x"], data["robot_loc_y"])).T

    d = playback_samples
    data = pd.read_table(d, delimiter=" ", header=None)
    data = data.T
    data.columns = ["x1", "x2", "z"]
    sample_loc = np.vstack((data["x1"], data["x2"])).T
    sample_val = data["z"].T

    # Initialize the robot's GP model with the initial kernel parameters
    extent = (0.0, 10.0, 0.0, 10.0)
    init_variance = 100.0
    init_lengthscale = 1.0
    noise = 1.001
    GP = gplib.OnlineGPModel(
        ranges=extent, lengthscale=init_lengthscale, variance=init_variance, noise=noise
    )

    t_sample_locs = {}
    t_sample_vals = {}
    value_robot = []

    S = 0
    E = 0
    for t, end_loc in enumerate(robot_loc[1:, :]):
        # Get next stop point in stream
        while not np.isclose(sample_loc[E, 0], end_loc[0]) or not np.isclose(
            sample_loc[E, 1], end_loc[1]
        ):
            E += 1
        E += 1

        t_sample_locs[t] = sample_loc[S:E, :]
        t_sample_vals[t] = np.array((sample_val[S:E])).astype("float")
        S = E
        E += 1

        # print "--------------", t, "-----------------"
        # print t_sample_locs[t]
        # print t_sample_vals[t]

        value_robot.append(
            aqlib.mves(
                time=t,
                xvals=t_sample_locs[t],
                robot_model=GP,
                param=(np.array(max_val)).reshape(1, 1),
            )
        )
        GP.add_data(
            t_sample_locs[t],
            np.reshape(t_sample_vals[t], (t_sample_locs[t].shape[0], 1)),
        )

    t = 149
    t_sample_locs[t] = sample_loc[S:, :]
    t_sample_vals[t] = np.array((sample_val[S:])).astype("float")
    # print "--------------", t, "-----------------"
    # print t_sample_locs[t]
    # print t_sample_vals[t]

    value_robot.append(
        aqlib.mves(
            time=t,
            xvals=t_sample_locs[t],
            robot_model=GP,
            param=(np.array(max_val)).reshape(1, 1),
        )
    )
    # GP.add_data(t_sample_locs[t], np.reshape(t_sample_vals[t], (t_sample_locs[t].shape[0], 1)))

    return np.cumsum(value_robot)


######### MAIN LOOP ###########
if __name__ == "__main__":
    seed_numbers = list(range(5000, 10000, 100))
    seeds = ["seed" + str(x) + "-" for x in seed_numbers]
    print(seeds)

    # fileparams = 'pathsetfully_reachable_goal-costTrue-nonmyopicFalse-goalFalse'
    # fileparams = 'pathsetdubins-costFalse-nonmyopicTrue-goalFalse_BUGTRAP'
    # fileparams = 'pathsetdubins-costFalse-nonmyopicTrue-goalFalse'
    file_start = "freeworld-dubins-nonmyopic"
    fileparams = "pathsetdubins-nonmyopicTrue-FREE"

    # path= '/home/genevieve/mit-whoi/informative-path-planning/experiments/'
    path = "/media/genevieve/WINDOWS_COM/IROS_2019/experiments/"
    # path= '/home/vpreston/Documents/IPP/informative-path-planning/experiments/'

    # get the data files
    f_mean = []
    f_mes = []

    mean_samples = []
    mes_samples = []

    max_val = []
    max_loc = []

    for root, dirs, files in os.walk(path):
        for name in files:
            if (
                "metrics.csv" in name
                and fileparams in root
                and "mean" in root
                and "old_fully_reachable" not in root
            ):
                for s in seeds:
                    if str(s) in root:
                        f_mean.append(root + "/" + name)
            # elif 'metric' in name and 'pathsetdubins-costFalse-nonmyopicFalse' in root and 'exp_improve' in dirs:
            #     f_ei.append(root + "/" + name)
            elif (
                "metrics.csv" in name
                and fileparams in root
                and "mes" in root
                and "old_fully_reachable" not in root
            ):
                for s in seeds:
                    if str(s) in root:
                        f_mes.append(root + "/" + name)
            ######## Looking at Samples ######
            elif (
                "robot_model" in name
                and "mean" in root
                and fileparams in root
                and "old_fully_reachable" not in root
            ):
                for s in seeds:
                    if str(s) in root:
                        mean_samples.append(root + "/" + name)
            # elif 'robot_model' in name and 'exp_improve' in root:
            #     ei_samples.append(root+"/"+name)
            elif (
                "robot_model" in name
                and "mes" in root
                and fileparams in root
                and "old_fully_reachable" not in root
            ):
                for s in seeds:
                    if str(s) in root:
                        mes_samples.append(root + "/" + name)
            ######## Looking at Mean values ######
            # get the robot log files
            elif (
                "log" in name
                and "mean" in root
                and fileparams in root
                and "old_fully_reachable" not in root
            ):
                for s in seeds:
                    ls = []
                    if str(s) in root:
                        temp = open(root + "/" + name, "r")
                        for l in temp.readlines():
                            if "max value" in l:
                                ls.append(l)
                        max_val.append(float(ls[-1].split(" ")[3]))
                        # For Genevieve
                        max_loc.append(
                            (
                                float(ls[-1].split(" ")[7].split("[")[0]),
                                float(ls[-1].split(" ")[9].split("]")[0]),
                            )
                        )
                        # For Victoria
                        # max_loc.append((float(ls[0].split(" ")[6].split("[")[1]), float(ls[0].split(" ")[7].split("]")[0])))

    # variables for making dataframes
    column_names = [
        "time",
        "info_gain",
        "aqu_fun",
        "MSE",
        "hotspot_error",
        "max_loc_error",
        "max_val_error",
        "simple_regret",
        "sample_regret_loc",
        "sample_regret_val",
        "regret",
        "info_regret",
        "current_highest_obs",
        "current_highest_obs_loc_x",
        "current_highest_obs_loc_y",
        "robot_loc_x",
        "robot_loc_y",
        "robot_loc_a",
        "distance",
        "max_value_info",
    ]

    mean_data = make_df(f_mean, mean_samples, max_val, column_names)
    mes_data = make_df(f_mes, mes_samples, max_val, column_names)
    print_stats(mean_data, mes_data, None, column_names, 149, file_start + "_stats.txt")

    mean_sdata, mean_prop = make_samples_df(mean_samples, ["x", "y", "a"], max_loc, 1.5)
    mes_sdata, mes_prop = make_samples_df(mes_samples, ["x", "y", "a"], max_loc, 1.5)
    # ei_sdata, ei_prop = make_samples_df(ei_samples, ['x', 'y', 'a'], max_loc, 1.5)

    print("Mean value of sample proportions: ")
    # print [sum(m)/len(m) for m in (mean_prop, mes_prop, ei_prop)]
    print([sum(m) / len(m) for m in (mean_prop, mes_prop)])
    print("STD value of sample proportions: ")
    # print [np.std(m) for m in (mean_prop, mes_prop, ei_prop)]
    print([np.std(m) for m in (mean_prop, mes_prop)])

    # make_histograms(mean_sdata, mes_sdata, ei_sdata)
    make_histograms(mean_sdata, mes_sdata, None, figname=file_start)

    # ######### Looking at Mission Progression ######
    make_plots(
        mean_data,
        mes_data,
        None,
        "max_val_error",
        "Averaged Maximum Value Error, Conf",
        len(seeds),
        True,
        True,
        fname=file_start + "_avg_valerr_conf",
    )
    make_plots(
        mean_data,
        mes_data,
        None,
        "max_loc_error",
        "Averaged Maximum Location Error, Conf",
        len(seeds),
        True,
        True,
        fname=file_start + "_avg_valloc_conf",
    )
    make_plots(
        mean_data,
        mes_data,
        None,
        "info_regret",
        "Averaged Information Regret, Conf",
        len(seeds),
        True,
        True,
        fname=file_start + "_avg_reg_conf",
    )
    make_plots(
        mean_data,
        mes_data,
        None,
        "MSE",
        "Averaged MSE, Conf",
        len(seeds),
        True,
        True,
        fname=file_start + "_avg_mse_conf",
    )
    make_plots(
        mean_data,
        mes_data,
        None,
        "max_value_info",
        "Averaged Max-Value Info, Conf",
        len(seeds),
        True,
        True,
        fname=file_start + "_avg_maxval_info_conf",
    )
    plt.show()
