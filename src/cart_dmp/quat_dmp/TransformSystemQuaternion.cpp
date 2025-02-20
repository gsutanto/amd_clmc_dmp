#include "dmp/cart_dmp/quat_dmp/TransformSystemQuaternion.h"

#include <memory>

#include "dmp/dmp_state/QuaternionDMPState.h"

namespace dmp {

TransformSystemQuaternion::TransformSystemQuaternion()
    : TransformSystemDiscrete() {}

TransformSystemQuaternion::TransformSystemQuaternion(
    CanonicalSystemDiscrete* canonical_system_discrete,
    std::unique_ptr<FuncApproximatorDiscrete> func_approximator_discrete,
    LoggedDMPDiscreteVariables* logged_dmp_discrete_vars,
    RealTimeAssertor* real_time_assertor,
    std::vector<bool> is_using_scaling_init,
    std::vector<TransformCoupling*>* transform_couplers, double ts_alpha,
    double ts_beta)
    : TransformSystemDiscrete(
          3, canonical_system_discrete, std::move(func_approximator_discrete),
          logged_dmp_discrete_vars, real_time_assertor, is_using_scaling_init,
          std::make_unique<QuaternionDMPState>(real_time_assertor),
          std::make_unique<QuaternionDMPState>(real_time_assertor),
          std::make_unique<DMPState>(3, real_time_assertor), nullptr,
          transform_couplers, ts_alpha, ts_beta, _SCHAAL_DMP_) {
  goal_sys =
      std::make_unique<QuaternionGoalSystem>(tau_sys, real_time_assertor);
}

bool TransformSystemQuaternion::isValid() {
  if (rt_assert(TransformSystemDiscrete::isValid()) == false) {
    return false;
  }
  if (rt_assert(dmp_num_dimensions == 3) == false) {
    return false;
  }
  if (rt_assert(formulation_type == _SCHAAL_DMP_) == false) {
    return false;
  }
  if (rt_assert(
          (rt_assert((static_cast<QuaternionDMPState*>(start_state.get()))
                         ->isValid())) &&
          (rt_assert((static_cast<QuaternionDMPState*>(current_state.get()))
                         ->isValid())) &&
          (rt_assert(current_velocity_state->isValid()))) == false) {
    return false;
  }
  if (rt_assert(
          (static_cast<QuaternionGoalSystem*>(goal_sys.get()))->isValid()) ==
      false) {
    return false;
  }
  return true;
}

bool TransformSystemQuaternion::startTransformSystemQuaternion(
    const QuaternionDMPState& start_state_init,
    const QuaternionDMPState& goal_state_init) {
  // pre-conditions checking
  if (rt_assert(this->isValid()) == false) {
    return false;
  }
  // input checking
  if (rt_assert((rt_assert(start_state_init.isValid())) &&
                (rt_assert(goal_state_init.isValid()))) == false) {
    return false;
  }
  if (rt_assert((rt_assert(start_state_init.getDMPNumDimensions() ==
                           dmp_num_dimensions)) &&
                (rt_assert(goal_state_init.getDMPNumDimensions() ==
                           dmp_num_dimensions))) == false) {
    return false;
  }

  *(static_cast<QuaternionDMPState*>(start_state.get())) = start_state_init;
  if (rt_assert(TransformSystemQuaternion::setCurrentQuaternionState(
          start_state_init)) == false) {
    return false;
  }

  Vector4 QG_init = goal_state_init.getQ();
  QuaternionDMPState current_goal_state_init(rt_assertor);
  if (func_approx_discrete->getCanonicalSystemDiscreteOrder() == 2) {
    // Best option for Schaal's DMP Model using 2nd order canonical system:
    // Using goal evolution system initialized with the start position (state)
    // as goal position (state), which over time evolves toward a steady-state
    // goal position (state). The main purpose is to avoid discontinuous initial
    // acceleration (see the math formula of Schaal's DMP Model for more
    // details). Please also refer the initialization described in paper: B.
    // Nemec and A. Ude, “Action sequencing using dynamic movement primitives,”
    // Robotica, vol. 30, no. 05, pp. 837–846, 2012.
    Vector4 Q0 = start_state_init.getQ();
    Vector3 omega0 = start_state_init.getOmega();
    Vector3 omegad0 = start_state_init.getOmegad();

    double tau;
    if (rt_assert(tau_sys->getTauRelative(tau)) == false) {
      return false;
    }

    Vector3 log_quat_diff_Qg_and_Q =
        ((((tau * tau * omegad0) / alpha) + (tau * omega0)) / beta);
    Vector4 quat_diff_Qg_and_Q = ZeroVector4;
    if (rt_assert(computeExpMap_so3_to_SO3(log_quat_diff_Qg_and_Q,
                                           quat_diff_Qg_and_Q)) == false) {
      return false;
    }
    Vector4 Qg0 = computeQuaternionComposition(quat_diff_Qg_and_Q, Q0);
    if (rt_assert(current_goal_state_init.setQ(Qg0)) == false) {
      return false;
    }
    if (rt_assert(current_goal_state_init.computeQdAndQdd()) == false) {
      return false;
    }
  } else {
    // Best option for Schaal's DMP Model using 1st order canonical system:
    // goal position is static, no evolution
    current_goal_state_init = goal_state_init;
  }

  if (rt_assert((static_cast<QuaternionGoalSystem*>(goal_sys.get()))
                    ->startQuaternionGoalSystem(current_goal_state_init,
                                                QG_init)) == false) {
    return false;
  }

  is_started = true;

  // post-conditions checking
  return (rt_assert(this->isValid()));
}

bool TransformSystemQuaternion::getNextQuaternionState(
    double dt, QuaternionDMPState& next_state, VectorN* forcing_term,
    VectorN* coupling_term_acc, VectorN* coupling_term_vel,
    VectorM* basis_functions_out,
    VectorM* normalized_basis_func_vector_mult_phase_multiplier) {
  // pre-conditions checking
  if (rt_assert(is_started == true) == false) {
    return false;
  }
  if (rt_assert(this->isValid()) == false) {
    return false;
  }
  // input checking
  if (rt_assert(next_state.isValid()) == false) {
    return false;
  }
  if (rt_assert(next_state.getDMPNumDimensions() == dmp_num_dimensions) ==
      false) {
    return false;
  }
  if (rt_assert(dt > 0.0) == false)  // dt does NOT make sense
  {
    return false;
  }

  double tau;
  if (rt_assert(tau_sys->getTauRelative(tau)) == false) {
    return false;
  }

  VectorN f(dmp_num_dimensions);
  VectorM basis_functions(func_approx_discrete->getModelSize());
  if (rt_assert(func_approx_discrete->getForcingTerm(
          f, &basis_functions,
          normalized_basis_func_vector_mult_phase_multiplier)) == false) {
    return false;
  }
  if (forcing_term) {
    (*forcing_term) = f;
  }
  if (basis_functions_out) {
    (*basis_functions_out) = basis_functions;
  }

  VectorN ct_acc(dmp_num_dimensions);
  VectorN ct_vel(dmp_num_dimensions);
  ct_acc = ZeroVectorN(dmp_num_dimensions);
  ct_vel = ZeroVectorN(dmp_num_dimensions);  // NOT used yet
  if (rt_assert(TransformationSystem::getCouplingTerm(ct_acc, ct_vel)) ==
      false) {
    return false;
  }
  for (uint d = 0; d < dmp_num_dimensions; ++d) {
    if (is_using_coupling_term_at_dimension[d] == false) {
      ct_acc[d] = 0;
      ct_vel[d] = 0;
    }
  }
  if (coupling_term_acc) {
    (*coupling_term_acc) = ct_acc;
  }
  if (coupling_term_vel) {
    (*coupling_term_vel) = ct_vel;
  }

  // some aliases:
  const QuaternionDMPState& start_quat_state =
      *(static_cast<QuaternionDMPState*>(start_state.get()));
  QuaternionDMPState& current_quat_state =
      *(static_cast<QuaternionDMPState*>(current_state.get()));
  DMPState& current_angular_velocity_state = *current_velocity_state;
  QuaternionGoalSystem* quat_goal_sys =
      (static_cast<QuaternionGoalSystem*>(goal_sys.get()));

  double time = current_quat_state.getTime();
  Vector4 Q0 = start_quat_state.getQ();
  Vector4 Q = current_quat_state.getQ();
  Vector3 omega = current_quat_state.getOmega();
  Vector3 omegad = current_quat_state.getOmegad();

  Vector3 etha = current_angular_velocity_state.getX();
  Vector3 ethad = current_angular_velocity_state.getXd();

  Vector4 QG = quat_goal_sys->getSteadyStateGoalPosition();
  Vector4 Qg = quat_goal_sys->getCurrentQuaternionGoalState().getQ();

  if (rt_assert(integrateQuaternion(Q, omega, dt, Q)) == false) {
    return false;
  }
  omega = omega + (omegad * dt);
  etha = tau * omega;  // ct_vel is NOT used yet!

  // compute scaling factor for the forcing term:
  Vector3 A = ZeroVector3;
  if (rt_assert(computeLogQuaternionDifference(QG, Q0, A)) == false) {
    return false;
  }

  for (uint n = 0; n < dmp_num_dimensions; ++n) {
    // The below hard-coded IF statement might still need improvement...
    if (is_using_scaling[n]) {
      if (fabs(A_learn[n]) <
          MIN_FABS_AMPLITUDE)  // if goal state position is too close from the
                               // start state position
      {
        A[n] = 1.0;
      } else {
        A[n] = A[n] / A_learn[n];
      }
    } else {
      A[n] = 1.0;
    }
  }

  // original formulation by Schaal, AMAM 2003
  Vector3 log_quat_diff_Qg_and_Q = ZeroVector3;
  if (rt_assert(computeLogQuaternionDifference(
          Qg, Q, log_quat_diff_Qg_and_Q)) == false) {
    return false;
  }
  ethad = ((alpha * ((beta * log_quat_diff_Qg_and_Q) - etha)) +
           ((f).asDiagonal() * A) + ct_acc) /
          tau;

  if (rt_assert(containsNaN(ethad) == false) == false) {
    return false;
  }

  omegad = ethad / tau;

  time = time + dt;

  current_quat_state = QuaternionDMPState(Q, omega, omegad, time, rt_assertor);
  if (rt_assert(current_quat_state.computeQdAndQdd()) == false) {
    return false;
  }
  current_angular_velocity_state =
      DMPState(etha, ethad, ZeroVectorN(dmp_num_dimensions), time, rt_assertor);
  next_state = current_quat_state;

  /**************** For Trajectory Data Logging Purposes (Start)
   * ****************/
  //        logged_dmp_discrete_variables->tau                              =
  //        tau; logged_dmp_discrete_variables->transform_sys_state_local =
  //        current_state; logged_dmp_discrete_variables->canonical_sys_state[0]
  //        = ((CanonicalSystemDiscrete*) canonical_sys)->getX();
  //        logged_dmp_discrete_variables->canonical_sys_state[1]           =
  //        ((CanonicalSystemDiscrete*) canonical_sys)->getXd();
  //        logged_dmp_discrete_variables->canonical_sys_state[2]           =
  //        ((CanonicalSystemDiscrete*) canonical_sys)->getXdd();
  //        logged_dmp_discrete_variables->goal_state_local                 =
  //        goal_sys->getCurrentGoalState();
  //        logged_dmp_discrete_variables->steady_state_goal_position_local = G;
  //        logged_dmp_discrete_variables->forcing_term                     = f;
  //        logged_dmp_discrete_variables->basis_functions                  =
  //        basis_functions; logged_dmp_discrete_variables->transform_sys_ct_acc
  //        = ct_acc;
  /**************** For Trajectory Data Logging Purposes (End) ****************/

  // post-conditions checking
  return (rt_assert(this->isValid()));
}

bool TransformSystemQuaternion::getTargetQuaternionForcingTerm(
    const QuaternionDMPState& current_state_demo_local, VectorN& f_target) {
  // pre-conditions checking
  if (rt_assert(is_started == true) == false) {
    return false;
  }
  if (rt_assert(this->isValid()) == false) {
    return false;
  }
  // input checking
  if (rt_assert(current_state_demo_local.isValid()) == false) {
    return false;
  }
  if (rt_assert(current_state_demo_local.getDMPNumDimensions() ==
                dmp_num_dimensions) == false) {
    return false;
  }
  if (rt_assert(f_target.rows() == dmp_num_dimensions) == false) {
    return false;
  }

  double tau_demo;
  if (rt_assert(tau_sys->getTauRelative(tau_demo)) == false) {
    return false;
  }

  // some aliases:
  QuaternionGoalSystem* quat_goal_sys =
      (static_cast<QuaternionGoalSystem*>(goal_sys.get()));

  // Vector4 Q0_demo = start_quat_state.getQ();
  Vector4 Q_demo = current_state_demo_local.getQ();
  Vector3 omega_demo = current_state_demo_local.getOmega();
  Vector3 omegad_demo = current_state_demo_local.getOmegad();

  Vector4 Qg_demo = quat_goal_sys->getCurrentQuaternionGoalState().getQ();

  // during learning, QG = QG_learn and Q0 = Q0_learn,
  // thus amplitude   = (computeLogQuaternionDifference(QG,
  // Q0)/computeLogQuaternionDifference(QG_learn, Q0_learn))
  //                  = (computeLogQuaternionDifference(QG, Q0)/A_learn) =
  //                  OnesVectorN(3),
  // as follows (commented out for computational effiency):
  // A_demo      = OnesVectorN(3);

  // original formulation by Schaal, AMAM 2003
  Vector3 log_quat_diff_Qg_demo_and_Q_demo = ZeroVector3;
  if (rt_assert(computeLogQuaternionDifference(
          Qg_demo, Q_demo, log_quat_diff_Qg_demo_and_Q_demo)) == false) {
    return false;
  }
  f_target = ((tau_demo * tau_demo * omegad_demo) -
              (alpha * ((beta * log_quat_diff_Qg_demo_and_Q_demo) -
                        (tau_demo * omega_demo))));
  /*for (uint n = 0; n < dmp_num_dimensions; ++n)
  {
      f_target[n] /= A_demo[n];
  }*/

  return true;
}

bool TransformSystemQuaternion::getTargetQuaternionCouplingTerm(
    const QuaternionDMPState& current_state_demo_local,
    VectorN& ct_acc_target) {
  // pre-conditions checking
  if (rt_assert(is_started == true) == false) {
    return false;
  }
  if (rt_assert(this->isValid()) == false) {
    return false;
  }
  // input checking
  if (rt_assert(current_state_demo_local.isValid()) == false) {
    return false;
  }
  if (rt_assert(current_state_demo_local.getDMPNumDimensions() ==
                dmp_num_dimensions) == false) {
    return false;
  }
  if (rt_assert(ct_acc_target.rows() == dmp_num_dimensions) == false) {
    return false;
  }

  double tau_demo;
  if (rt_assert(tau_sys->getTauRelative(tau_demo)) == false) {
    return false;
  }

  VectorN f(dmp_num_dimensions);
  if (rt_assert(func_approx_discrete->getForcingTerm(f)) == false) {
    return false;
  }

  // some aliases:
  const QuaternionDMPState& start_quat_state =
      *(static_cast<QuaternionDMPState*>(start_state.get()));
  QuaternionGoalSystem* quat_goal_sys =
      (static_cast<QuaternionGoalSystem*>(goal_sys.get()));

  Vector4 Q0_demo = start_quat_state.getQ();
  Vector4 Q_demo = current_state_demo_local.getQ();
  Vector3 omega_demo = current_state_demo_local.getOmega();
  Vector3 omegad_demo = current_state_demo_local.getOmegad();

  Vector4 QG_demo = quat_goal_sys->getSteadyStateGoalPosition();
  Vector4 Qg_demo = quat_goal_sys->getCurrentQuaternionGoalState().getQ();

  // compute scaling factor for the forcing term:
  Vector3 A_demo = ZeroVector3;
  if (rt_assert(computeLogQuaternionDifference(QG_demo, Q0_demo, A_demo)) ==
      false) {
    return false;
  }

  for (uint n = 0; n < dmp_num_dimensions; ++n) {
    // The below hard-coded IF statement might still need improvement...
    if (is_using_scaling[n]) {
      if (fabs(A_learn[n]) <
          MIN_FABS_AMPLITUDE)  // if goal state position is too close from the
                               // start state position
      {
        A_demo[n] = 1.0;
      } else {
        A_demo[n] = A_demo[n] / A_learn[n];
      }
    } else {
      A_demo[n] = 1.0;
    }
  }

  // original formulation by Schaal, AMAM 2003
  Vector3 log_quat_diff_Qg_demo_and_Q_demo = ZeroVector3;
  if (rt_assert(computeLogQuaternionDifference(
          Qg_demo, Q_demo, log_quat_diff_Qg_demo_and_Q_demo)) == false) {
    return false;
  }
  ct_acc_target = ((tau_demo * tau_demo * omegad_demo) -
                   (alpha * ((beta * log_quat_diff_Qg_demo_and_Q_demo) -
                             (tau_demo * omega_demo))) -
                   ((f).asDiagonal() * A_demo));

  for (uint d = 0; d < dmp_num_dimensions; ++d) {
    if (is_using_coupling_term_at_dimension[d] == false) {
      ct_acc_target[d] = 0;
    }
  }

  return true;
}

QuaternionDMPState TransformSystemQuaternion::getQuaternionStartState() {
  QuaternionDMPState start_quat_state =
      *(static_cast<QuaternionDMPState*>(start_state.get()));
  return start_quat_state;
}

bool TransformSystemQuaternion::setQuaternionStartState(
    const QuaternionDMPState& new_start_state) {
  // some aliases:
  QuaternionDMPState& start_quat_state =
      *(static_cast<QuaternionDMPState*>(start_state.get()));

  // pre-conditions checking
  if (rt_assert(this->isValid()) == false) {
    return false;
  }
  // input checking
  if (rt_assert(new_start_state.isValid()) == false) {
    return false;
  }
  if (rt_assert(start_quat_state.getDMPNumDimensions() ==
                new_start_state.getDMPNumDimensions()) == false) {
    return false;
  }

  start_quat_state = new_start_state;

  // post-condition(s) checking
  return (rt_assert(this->isValid()));
}

QuaternionDMPState TransformSystemQuaternion::getCurrentQuaternionState() {
  QuaternionDMPState current_quat_state =
      *(static_cast<QuaternionDMPState*>(current_state.get()));
  return current_quat_state;
}

bool TransformSystemQuaternion::setCurrentQuaternionState(
    const QuaternionDMPState& new_current_state) {
  // some aliases:
  QuaternionDMPState& current_quat_state =
      *(static_cast<QuaternionDMPState*>(current_state.get()));

  // pre-conditions checking
  if (rt_assert(this->isValid()) == false) {
    return false;
  }
  // input checking
  if (rt_assert(new_current_state.isValid()) == false) {
    return false;
  }
  if (rt_assert(current_quat_state.getDMPNumDimensions() ==
                new_current_state.getDMPNumDimensions()) == false) {
    return false;
  }

  current_quat_state = new_current_state;

  if (rt_assert(this->updateCurrentVelocityStateFromCurrentState()) == false) {
    return false;
  }

  // post-condition(s) checking
  return (rt_assert(this->isValid()));
}

bool TransformSystemQuaternion::updateCurrentVelocityStateFromCurrentState() {
  // some aliases:
  const QuaternionDMPState& current_quat_state =
      *(static_cast<QuaternionDMPState*>(current_state.get()));
  DMPState& current_angular_velocity_state = *current_velocity_state;

  // pre-conditions checking
  if (rt_assert(this->isValid()) == false) {
    return false;
  }

  double tau;
  if (rt_assert(tau_sys->getTauRelative(tau)) == false) {
    return false;
  }

  Vector3 omega = current_quat_state.getOmega();
  Vector3 omegad = current_quat_state.getOmegad();

  Vector3 etha = tau * omega;
  Vector3 ethad = tau * omegad;

  if (rt_assert(current_angular_velocity_state.setX(etha)) == false) {
    return false;
  }
  if (rt_assert(current_angular_velocity_state.setXd(ethad)) == false) {
    return false;
  }

  // post-conditions checking
  return (rt_assert(this->isValid()));
}

QuaternionDMPState TransformSystemQuaternion::getCurrentQuaternionGoalState() {
  // some aliases:
  QuaternionGoalSystem* quat_goal_sys =
      (static_cast<QuaternionGoalSystem*>(goal_sys.get()));
  return (quat_goal_sys->getCurrentQuaternionGoalState());
}

bool TransformSystemQuaternion::setCurrentQuaternionGoalState(
    const QuaternionDMPState& new_current_goal_state) {
  // some aliases:
  QuaternionGoalSystem* quat_goal_sys =
      (static_cast<QuaternionGoalSystem*>(goal_sys.get()));
  return (rt_assert(
      quat_goal_sys->setCurrentQuaternionGoalState(new_current_goal_state)));
}

TransformSystemQuaternion::~TransformSystemQuaternion() {}

}  // namespace dmp
