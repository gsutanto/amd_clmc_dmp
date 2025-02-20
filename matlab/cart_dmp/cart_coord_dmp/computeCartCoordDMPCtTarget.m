function [ cart_coord_Ct_target ]  = computeCartCoordDMPCtTarget( cart_coord_demo_coupled_traj_global,...
                                                                  cart_coord_dmp_baseline_params )
    [ cart_coord_demo_coupled_traj_local ]  = convertCTrajAtOldToNewCoordSys( cart_coord_demo_coupled_traj_global, ...
                                                                              cart_coord_dmp_baseline_params.T_global_to_local_H );
    
    Yc_local    = cart_coord_demo_coupled_traj_local{1,1};
    Ycd_local   = cart_coord_demo_coupled_traj_local{2,1};
    Ycdd_local  = cart_coord_demo_coupled_traj_local{3,1};
    [ cart_coord_Ct_target, ~ ] = computeDMPCtTarget(   Yc_local, ...
                                                        Ycd_local, ...
                                                        Ycdd_local, ...
                                                        cart_coord_dmp_baseline_params.w, ...
                                                        cart_coord_dmp_baseline_params.n_rfs, ...
                                                        cart_coord_dmp_baseline_params.mean_start_local, ...
                                                        cart_coord_dmp_baseline_params.mean_goal_local, ...
                                                        cart_coord_dmp_baseline_params.dt, ...
                                                        cart_coord_dmp_baseline_params.c_order );
end