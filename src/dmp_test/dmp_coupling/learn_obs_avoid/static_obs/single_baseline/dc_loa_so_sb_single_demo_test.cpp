#include <getopt.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#include <iostream>

#include "dmp/cart_dmp/cart_coord_dmp/CartesianCoordDMP.h"
#include "dmp/cart_dmp/cart_coord_dmp/CartesianCoordTransformer.h"
#include "dmp/dmp_coupling/learn_obs_avoid/TransformCouplingLearnObsAvoid.h"
#include "dmp/dmp_discrete/CanonicalSystemDiscrete.h"
#include "dmp/dmp_state/DMPState.h"
#include "dmp/paths.h"
#include "dmp/utility/RealTimeAssertor.h"
#include "dmp/utility/utility.h"

using namespace dmp;

void print_usage() {
  printf(
      "Usage: dmp_dc_loa_so_sb_single_demo_demo [-f formula_type(0=_SCHAAL_ OR "
      "1=_HOFFMANN_)] [-c canonical_order(1 OR 2)] [-m "
      "learning_method(0=_SCHAAL_LWR_METHOD_ OR "
      "1=_JPETERS_GLOBAL_LEAST_SQUARES_METHOD_)] [-o loa_plot_dir_path] [-e "
      "rt_err_file_path]\n");
}

int main(int argc, char** argv) {
  bool is_real_time = false;

  double task_servo_rate = 420.0;  // MasterArm robot's task servo rate
  double dt = 1.0 / task_servo_rate;
  uint model_size = 25;

  uint formula_type = _SCHAAL_DMP_;
  // uint        formula_type                = _HOFFMANN_DMP_;
  uint canonical_order = 2;  // default is using 2nd order canonical system
  uint learning_method = _SCHAAL_LWR_METHOD_;
  char loa_data_dir_path[1000];
  std::string loa_data_dir_path_str = 
    get_data_path("/dmp_coupling/learn_obs_avoid/static_obs/data_sph_new/SubjectNo1/");
  snprintf(loa_data_dir_path, sizeof(loa_data_dir_path),
           "%s", loa_data_dir_path_str.c_str());
  char loa_plot_dir_path[1000];
  std::string loa_plot_dir_path_str = 
    get_plot_path("/dmp_coupling/learn_obs_avoid/feature_trajectory/static_obs/"
                 "single_baseline/single_demo/");
  snprintf(loa_plot_dir_path, sizeof(loa_plot_dir_path),
           "%s", loa_plot_dir_path_str.c_str());
  char rt_err_file_path[1000];
  std::string rt_err_file_path_str = 
    get_rt_errors_path("/rt_err.txt");
  snprintf(rt_err_file_path, sizeof(rt_err_file_path),
           "%s", rt_err_file_path_str.c_str());

  uint AF_H14_feature_method = _AF_H14_NO_PHI3_;

  double tau_reproduce = 5.0;

  VectorN start_position;
  VectorN goal_position;

  Vector3 obsctr_cart_position_global;
  double obs_sphere_radius = 0.05;
  Matrix4x4 ctraj_hmg_transform_global_to_local_matrix;

  static struct option long_options[] = {
      {"formula_type", required_argument, 0, 'f'},
      {"canonical_order", required_argument, 0, 'c'},
      {"learning_method", required_argument, 0, 'm'},
      {"loa_plot_dir_path", required_argument, 0, 'o'},
      {"rt_err_file_path", required_argument, 0, 'e'},
      {0, 0, 0, 0}};

  int opt = 0;
  int long_index = 0;
  while ((opt = getopt_long(argc, argv, "f:c:m:o:e:", long_options,
                            &long_index)) != -1) {
    switch (opt) {
      case 'f':
        formula_type = atoi(optarg);
        break;
      case 'c':
        canonical_order = atoi(optarg);
        break;
      case 'm':
        learning_method = atoi(optarg);
        break;
      case 'o':
        snprintf(loa_plot_dir_path, sizeof(loa_plot_dir_path), "%s", optarg);
        break;
      case 'e':
        snprintf(rt_err_file_path, sizeof(rt_err_file_path), "%s", optarg);
        break;
      default:
        print_usage();
        exit(EXIT_FAILURE);
    }
  }

  if ((formula_type < _SCHAAL_DMP_) || (formula_type > _HOFFMANN_DMP_) ||
      (canonical_order < 1) || (canonical_order > 2) ||
      (learning_method < _SCHAAL_LWR_METHOD_) ||
      (learning_method > _JPETERS_GLOBAL_LEAST_SQUARES_METHOD_) ||
      (strcmp(loa_plot_dir_path, "") == 0) ||
      (strcmp(rt_err_file_path, "") == 0)) {
    print_usage();
    exit(EXIT_FAILURE);
  }

  // Initialize real-time assertor
  RealTimeAssertor rt_assertor(rt_err_file_path);
  rt_assertor.clear_rt_err_file();

  DMPState ee_cart_state_global(3, &rt_assertor);
  DMPState obsctr_cart_state_global(3, &rt_assertor);

  ObstacleStates point_obstacles_cart_state_global(2);

  DataIO data_io_main(&rt_assertor);
  if (rt_assert_main(data_io_main.writeMatrixToFile(
          loa_plot_dir_path, "tau_reproduce.txt", tau_reproduce)) == false) {
    return rt_assertor.writeErrorsAndReturnIntErrorCode(-1);
  }

  // Initialize tau system
  TauSystem tau_sys(MIN_TAU, &rt_assertor);

  // Initialize canonical system
  CanonicalSystemDiscrete canonical_sys_discr(&tau_sys, &rt_assertor,
                                              canonical_order);

  TCLearnObsAvoidFeatureParameter tc_loa_feat_param(
      &rt_assertor, &canonical_sys_discr,
      _SPHERE_OBSTACLE_CENTER_RADIUS_FILE_FORMAT_, AF_H14_feature_method, 5, 5,
      (1.0 / M_PI), (5.0 / M_PI), 1.0, 3.0, 1, 3.0, 45.0);

  TransformCouplingLearnObsAvoid transform_coupling_learn_obs_avoid(
      &tc_loa_feat_param, &tau_sys, &ee_cart_state_global,
      &point_obstacles_cart_state_global,
      &ctraj_hmg_transform_global_to_local_matrix, &rt_assertor, false, true,
      loa_plot_dir_path);

  std::vector<TransformCoupling*> transform_couplers(1);

  // Initialize Cartesian Coordinate DMP
  CartesianCoordDMP cart_dmp(
      &canonical_sys_discr, model_size, formula_type, learning_method,
      &rt_assertor, _GSUTANTO_LOCAL_COORD_FRAME_, "", &transform_couplers);

  // Learn both the coupling term and the BASELINE DMP:
  if (rt_assert_main(transform_coupling_learn_obs_avoid.learnCouplingTerm(
          loa_data_dir_path, task_servo_rate, &cart_dmp, 5.0, true, 500, nullptr,
          0.3)) == false) {
    return rt_assertor.writeErrorsAndReturnIntErrorCode(-1);
  }

  MatrixNxMPtr weights_baseline;
  if (rt_assert_main(allocateMemoryIfNonRealTime(is_real_time, weights_baseline,
                                                 3, model_size)) == false) {
    return rt_assertor.writeErrorsAndReturnIntErrorCode(-1);
  }
  VectorN A_learn_baseline(3);

  weights_baseline->resize(3, model_size);
  if (rt_assert_main(cart_dmp.getParams(*weights_baseline, A_learn_baseline)) ==
      false) {
    return rt_assertor.writeErrorsAndReturnIntErrorCode(-1);
  }

  start_position = cart_dmp.getMeanStartPosition();
  goal_position = cart_dmp.getMeanGoalPosition();

  DMPState current_state(3, &rt_assertor);

  DMPUnrollInitParams dmp_unroll_init_parameters(
      tau_reproduce, DMPState(start_position, &rt_assertor),
      DMPState(goal_position, &rt_assertor), &rt_assertor);

  /****************** without obstacle (START) ******************/
  // NOT using obstacle avoidance coupling term:
  transform_couplers[0] = nullptr;
  if (rt_assert_main(cart_dmp.setParams(*weights_baseline, A_learn_baseline)) ==
      false) {
    return rt_assertor.writeErrorsAndReturnIntErrorCode(-1);
  }
  if (rt_assert_main(cart_dmp.start(dmp_unroll_init_parameters)) == false) {
    return rt_assertor.writeErrorsAndReturnIntErrorCode(-1);
  }

  // Run DMP and print state values:
  if (rt_assert_main(cart_dmp.startCollectingTrajectoryDataSet()) == false) {
    return rt_assertor.writeErrorsAndReturnIntErrorCode(-1);
  }
  for (uint i = 0; i < (round(tau_reproduce * task_servo_rate) + 1); ++i) {
    double time = 1.0 * (i * dt);

    // Get the next state of the Cartesian DMP
    if (rt_assert_main(cart_dmp.getNextState(dt, true, current_state)) ==
        false) {
      return rt_assertor.writeErrorsAndReturnIntErrorCode(-1);
    }

    // Log state trajectory:
    printf("%.05f %.05f %.05f %.05f\n", time, current_state.getX()[0],
           current_state.getX()[1], current_state.getX()[2]);
  }
  cart_dmp.stopCollectingTrajectoryDataSet();
  if (rt_assert_main(cart_dmp.saveTrajectoryDataSet(
          get_plot_path(
              "/dmp_coupling/learn_obs_avoid/tau_invariance_evaluation/wo_obs/")
              .c_str())) == false) {
    return rt_assertor.writeErrorsAndReturnIntErrorCode(-1);
  }
  /****************** without obstacle (END) ******************/

  /****************** with obstacle (START) ******************/
  // IMPORTANT PART here:
  // Here only one CartesianCoordDMP is used:
  // cart_dmp
  obsctr_cart_position_global[0] = 0.553216;
  obsctr_cart_position_global[1] = -0.016969;
  obsctr_cart_position_global[2] = 0.225269;
  obsctr_cart_state_global =
      DMPState(obsctr_cart_position_global, &rt_assertor);
  // Using obstacle avoidance coupling term:
  transform_couplers[0] = &transform_coupling_learn_obs_avoid;
  if (rt_assert_main(cart_dmp.setParams(*weights_baseline, A_learn_baseline)) ==
      false) {
    return rt_assertor.writeErrorsAndReturnIntErrorCode(-1);
  }
  if (rt_assert_main(cart_dmp.start(dmp_unroll_init_parameters)) == false) {
    return rt_assertor.writeErrorsAndReturnIntErrorCode(-1);
  }
  current_state = cart_dmp.getCurrentState();
  ctraj_hmg_transform_global_to_local_matrix =
      cart_dmp.getHomogeneousTransformMatrixGlobalToLocal();

  // Run DMP and print state values:
  if (rt_assert_main(transform_coupling_learn_obs_avoid
                         .startCollectingTrajectoryDataSet()) == false) {
    return rt_assertor.writeErrorsAndReturnIntErrorCode(-1);
  }
  if (rt_assert_main(cart_dmp.startCollectingTrajectoryDataSet()) == false) {
    return rt_assertor.writeErrorsAndReturnIntErrorCode(-1);
  }
  for (uint i = 0; i < (round(tau_reproduce * task_servo_rate) + 1); ++i) {
    double time = 1.0 * (i * dt);

    // IMPORTANT PART here:
    // Here ee_cart_state_global is updated.
    // Different from the "ideal" case before, here these variables are updated
    // using the current (or real-time) DMP unrolled trajectory. These variable
    // will in turn be used for computing the features of obstacle avoidance
    // coupling term. Thus the resulting obstacle avoidance coupling term is the
    // "realistic" one, i.e. i.e. conditioned with features computed with known
    // information.
    ee_cart_state_global = current_state;
    if (rt_assert_main(
            transform_coupling_learn_obs_avoid
                .computePointObstaclesCartStateGlobalFromStaticSphereObstacle(
                    ee_cart_state_global, obsctr_cart_state_global,
                    obs_sphere_radius, point_obstacles_cart_state_global)) ==
        false) {
      return rt_assertor.writeErrorsAndReturnIntErrorCode(-1);
    }

    // Get the next state of the Cartesian DMP
    if (rt_assert_main(cart_dmp.getNextState(dt, true, current_state)) ==
        false) {
      return rt_assertor.writeErrorsAndReturnIntErrorCode(-1);
    }

    // Log state trajectory:
    printf("%.05f %.05f %.05f %.05f\n", time, current_state.getX()[0],
           current_state.getX()[1], current_state.getX()[2]);
  }
  cart_dmp.stopCollectingTrajectoryDataSet();
  if (rt_assert_main(cart_dmp.saveTrajectoryDataSet(
          get_plot_path("/dmp_coupling/learn_obs_avoid/"
                        "tau_invariance_evaluation/w_obs_real/")
              .c_str())) == false) {
    return rt_assertor.writeErrorsAndReturnIntErrorCode(-1);
  }
  transform_coupling_learn_obs_avoid.stopCollectingTrajectoryDataSet();
  if (rt_assert_main(
          transform_coupling_learn_obs_avoid.saveTrajectoryDataSet()) ==
      false) {
    return rt_assertor.writeErrorsAndReturnIntErrorCode(-1);
  }
  /****************** with obstacle (END) ******************/

  return 0;
}
