% Cartesian (both Coordinate & Quaternion) Dynamic Movement Primitive (DMP) 
% Unrolling with a Trained Phase LWR Neural Network Feedback/Coupling Term 
% Simulation
% ---Given Baseline/Nominal Cartesian DMPs and Nominal Sensory Traces 
%    (also represented as (sensory-)primitives), simulate unrolling with 
%    a trained Phase LWR Neural Network Feedback/Coupling Term,
%    fed with actual sensory traces deviation from the nominal traces
%    (Associative Skill Memories/ASM(s)), as input---
% 
% Author : Giovanni Sutanto
% Date   : June 25, 2017

clear all;
close all;
clc;

rel_dir_path        = '../../';

addpath([rel_dir_path, '../../utilities/']);
addpath([rel_dir_path, '../../cart_dmp/cart_coord_dmp/']);
addpath([rel_dir_path, '../../cart_dmp/quat_dmp/']);
addpath([rel_dir_path, '../../dmp_multi_dim/']);
addpath([rel_dir_path, '../../neural_nets/feedforward/pmnn/']);

scraping_data_root_dir_path = [rel_dir_path, '../../../data/dmp_coupling/learn_tactile_feedback/scraping/'];

python_learn_tactile_fb_models_dir_path = [rel_dir_path, '../../../python/dmp_coupling/learn_tactile_feedback/models/'];

reinit_selection_idx        = dlmread([python_learn_tactile_fb_models_dir_path, 'reinit_selection_idx.txt']);
TF_max_train_iters          = dlmread([python_learn_tactile_fb_models_dir_path, 'TF_max_train_iters.txt']);

freq        = 300.0;    % ARM robot servo rate is 300 Hz
dt          = 1.0/freq;

D           = 3;
Dq          = 4;

N_prims     = 3;
N_fingers   = 2;

precision_string    = '%.20f';
%% DMP Parameter Setup

global      dcps;

n_rfs     	= 25;
c_order    	= 1;    % using 2nd order canonical system (for Cartesian position and orientation)

% end of DMP Parameter Setup
%% Load the Baseline Primitive Params to be Unrolled

load([rel_dir_path,'dmp_baseline_params_scraping.mat']);
load([rel_dir_path,'data_demo_scraping.mat']);
load([rel_dir_path,'dataset_Ct_tactile_asm_scraping.mat']);

% end of Load the Baseline Primitive Params to be Unrolled
%% Test Setting and Trial Number Particular Selection

setting_no  = 2;
trial_no    = 3;

unroll_test_data.position   = cell(N_prims, 1);
unroll_test_data.orientation= cell(N_prims, 1);
unroll_test_data.sense      = cell(N_prims, 3); 

% data binning and logging for C++ synchronization:
for n_prim = 1:N_prims
    unroll_test_data.position{n_prim, 1}	= data_demo.coupled{n_prim, setting_no}{trial_no,  2};
    unroll_test_data.orientation{n_prim, 1}	= data_demo.coupled{n_prim, setting_no}{trial_no,  3};
    unroll_test_data.sense{n_prim, 1}       = data_demo.coupled{n_prim, setting_no}{trial_no,  6};  % 1==BioTac R_LF_electrodes (Tactile Right Finger)
    unroll_test_data.sense{n_prim, 2}       = data_demo.coupled{n_prim, setting_no}{trial_no, 14};  % 2==BioTac R_RF_electrodes (Tactile Right Finger)
    unroll_test_data.sense{n_prim, 3}       = data_demo.coupled{n_prim, setting_no}{trial_no, 22};  % 3==Joint Positions/Coordinates (Proprioception)
end

% end of Test Setting and Trial Number Particular Selection

%% Computing Sensor Traces Deviation

N_points_ave_init_offset                = 5;

nominal_traces_unroll_cell              = cell(N_prims, 3);
sub_X_cell                              = cell(N_prims, 3);
phase_V_cell                            = cell(N_prims, 1);
phase_PSI_cell                          = cell(N_prims, 1);
X_cell                                  = cell(N_prims, 1);
normalized_phase_PSI_mult_phase_V_cell  = cell(N_prims, 1);
% BioTac Electrodes
for nf = 1:N_fingers
    for np = 1:N_prims
        % cancel offset in electrode traces (using primitive 1's initial
        % averaged offset for ALL primitives):
        if (np == 1)
            BT_electrode_signal_offset  = (1.0/N_points_ave_init_offset) * sum(unroll_test_data.sense{np, nf}(1:N_points_ave_init_offset,:),1);
        end
        unroll_test_data.sense{np, nf}  = unroll_test_data.sense{np, nf} - repmat(BT_electrode_signal_offset, size(unroll_test_data.sense{np, nf}, 1), 1);
        
        [nominal_traces_unroll_cell{np,nf},...
         ~,...
         phase_V_cell{np,1},...
         phase_PSI_cell{np,1}]  = unrollBaselineSensoryPrimitiveMatchingDemo(dmp_baseline_params.BT_electrode{np, nf}, ...
                                                                             unroll_test_data.sense{np, nf}, 0);
        sub_X_cell{np,nf}       = unroll_test_data.sense{np, nf} - nominal_traces_unroll_cell{np,nf};
    end
end

% Joints/Proprioception
for np = 1:N_prims
    [nominal_traces_unroll_cell{np,3}]  = unrollBaselineSensoryPrimitiveMatchingDemo(dmp_baseline_params.joint_sense{np, 1}, ...
                                                                                     unroll_test_data.sense{np, 3}, 0);
    sub_X_cell{np,3}	= unroll_test_data.sense{np, 3} - nominal_traces_unroll_cell{np,3};
end

for np = 1:N_prims
    X_cell{np,1}        = cell2mat(sub_X_cell(np,:));
    normalized_phase_PSI_mult_phase_V_cell{np,1}   = phase_PSI_cell{np,1} .* repmat((phase_V_cell{np,1} ./ sum((phase_PSI_cell{np,1}+1.e-10),2)),1,n_rfs);
end

% end of Computing Sensor Traces Deviation

%% PMNN Coupling Term Prediction

model_path  = [rel_dir_path, '../../../data/dmp_coupling/learn_tactile_feedback/scraping/neural_nets/pmnn/python_models/'];

Ctt_test_prediction_MATLAB_cell = cell(N_prims, 1);
NN_LWR_layer_cell_cell          = cell(N_prims, 1);

for np=1:N_prims
    D_input             = size(X_cell{np,1}, 2);
    regular_NN_hidden_layer_topology = dlmread([python_learn_tactile_fb_models_dir_path, 'regular_NN_hidden_layer_topology.txt']);
    N_phaseLWR_kernels  = size(normalized_phase_PSI_mult_phase_V_cell{np,1}, 2);
    D_output            = 6;
    
    regular_NN_hidden_layer_activation_func_list = readStringsToCell([python_learn_tactile_fb_models_dir_path, 'regular_NN_hidden_layer_activation_func_list.txt']);
    
    NN_info.name        = 'my_ffNNphaseLWR';
    NN_info.topology    = [D_input, regular_NN_hidden_layer_topology, N_phaseLWR_kernels, D_output];
    NN_info.activation_func_list= {'identity', regular_NN_hidden_layer_activation_func_list{:}, 'identity', 'identity'};
    NN_info.filepath    = [model_path, 'prim_', num2str(np), '_params_reinit_', num2str(reinit_selection_idx(1, np)), '_step_',num2str(TF_max_train_iters,'%07d'),'.mat'];

    [ Ctt_test_prediction_MATLAB_cell{np,1}, NN_LWR_layer_cell_cell{np,1} ] = performPMNNPrediction( NN_info, X_cell{np,1}, normalized_phase_PSI_mult_phase_V_cell{np,1} );
end

% end of PMNN Coupling Term Prediction

%% Unrolling with Coupling Terms on CartCoordDMP

cart_coord_dmp_params_cell                      = cell(N_prims, 1);
cart_coord_dmp_unroll_global_coupled_traj_cell  = cell(N_prims, 1);
cart_coord_dmp_unroll_local_coupled_traj_cell   = cell(N_prims, 1);

% use the first primitive's fitted initial position as the initial position of 
% the first primitive (and zero initial velocity and acceleration):
y0_global   = dmp_baseline_params.cart_coord{1, 1}.mean_start_global;
yd0_global  = zeros(3,1);
ydd0_global = zeros(3,1);

for np=1:N_prims
    cart_coord_dmp_params_basic.dt                  = dt;
    cart_coord_dmp_params_basic.n_rfs               = n_rfs;
    cart_coord_dmp_params_basic.c_order             = c_order;
    cart_coord_dmp_params_basic.w                   = dmp_baseline_params.cart_coord{np, 1}.w;
    cart_coord_dmp_params_basic.dG                  = zeros(1,3);   % turn-off scaling in all dimensions
    
    unroll_traj_length                              = size(Ctt_test_prediction_MATLAB_cell{np,1}, 1);
    
    unroll_cart_coord_params_basic.mean_tau         = dt * (unroll_traj_length - 1);
    unroll_cart_coord_params_basic.mean_start_global= y0_global;
    unroll_cart_coord_params_basic.mean_goal_global = dmp_baseline_params.cart_coord{np, 1}.mean_goal_global;
    unroll_cart_coord_params_basic.yd0_global       = yd0_global;
    unroll_cart_coord_params_basic.ydd0_global      = ydd0_global;
    unroll_cart_coord_params_basic.ctraj_local_coordinate_frame_selection   = dmp_baseline_params.cart_coord{np, 1}.ctraj_local_coordinate_frame_selection;
    
    [cart_coord_dmp_params_cell{np, 1}, ...
     cart_coord_dmp_unroll_global_coupled_traj_cell{np, 1}, ...
     cart_coord_dmp_unroll_local_coupled_traj_cell{np, 1}]  = unrollCartPrimitiveOnLocalCoord( cart_coord_dmp_params_basic, ...
                                                                                               unroll_cart_coord_params_basic, ...
                                                                                               Ctt_test_prediction_MATLAB_cell{np,1}(:,1:3) );
    
    % use the latest state in this primitive to become the initial state of 
    % the next primitive:
    y0_global   = cart_coord_dmp_unroll_global_coupled_traj_cell{np, 1}{1,1}(end,:).';
    yd0_global  = cart_coord_dmp_unroll_global_coupled_traj_cell{np, 1}{2,1}(end,:).';
    ydd0_global = cart_coord_dmp_unroll_global_coupled_traj_cell{np, 1}{3,1}(end,:).';
end

% end of Unrolling with Coupling Terms on CartCoordDMP

%% Unrolling with Coupling Terms on QuaternionDMP

Quat_dmp_unroll_coupled_traj_cell	= cell(N_prims, 1);

Q0                          = dmp_baseline_params.Quat{1, 1}.fit_mean_Q0;
omega0                      = zeros(3, 1);
omegad0                     = zeros(3, 1);

for np=1:N_prims
    Quat_dmp_params.dt          = dt;
    Quat_dmp_params.n_rfs       = n_rfs;
    Quat_dmp_params.c_order     = c_order;
    Quat_dmp_params.w           = dmp_baseline_params.Quat{np, 1}.w;
    Quat_dmp_params.dG          = zeros(3,1);   % turn-off scaling in all dimensions
    Quat_dmp_params.fit_mean_tau= dmp_baseline_params.Quat{np, 1}.fit_mean_tau;
    Quat_dmp_params.fit_mean_Q0 = dmp_baseline_params.Quat{np, 1}.fit_mean_Q0;
    Quat_dmp_params.fit_mean_QG = dmp_baseline_params.Quat{np, 1}.fit_mean_QG;
    
    unroll_traj_length        	= size(Ctt_test_prediction_MATLAB_cell{np,1}, 1);
    
    % Unrolling based on Dataset (using mean_Q0 and mean_QG)
    unroll_Quat_params.tau          = dt * (unroll_traj_length - 1);
    unroll_Quat_params.traj_length  = unroll_traj_length;
    unroll_Quat_params.start        = Q0;
    unroll_Quat_params.goal         = dmp_baseline_params.Quat{np, 1}.fit_mean_QG;
    unroll_Quat_params.omega0       = omega0;
    unroll_Quat_params.omegad0      = omegad0;
    
    [Quat_dmp_unroll_coupled_traj_cell{np, 1}]  = unrollQuatPrimitive( Quat_dmp_params, ...
                                                                       unroll_Quat_params, ...
                                                                       Ctt_test_prediction_MATLAB_cell{np,1}(:,4:6) );
    
    % use the latest state in this primitive to become the initial state of 
    % the next primitive:
    Q0                              = Quat_dmp_unroll_coupled_traj_cell{np, 1}{1,1}(end,:).';
    omega0                          = Quat_dmp_unroll_coupled_traj_cell{np, 1}{4,1}(end,:).';
    omegad0                         = Quat_dmp_unroll_coupled_traj_cell{np, 1}{5,1}(end,:).';
end

% end of Unrolling with Coupling Terms on QuaternionDMP

%% Nominal Unrolling on CartCoordDMP

cart_coord_dmp_params_cell                      = cell(N_prims, 1);
cart_coord_dmp_unroll_global_nominal_traj_cell  = cell(N_prims, 1);
cart_coord_dmp_unroll_local_nominal_traj_cell   = cell(N_prims, 1);

% use the first primitive's fitted initial position as the initial position of 
% the first primitive (and zero initial velocity and acceleration):
y0_global   = dmp_baseline_params.cart_coord{1, 1}.mean_start_global;
yd0_global  = zeros(3,1);
ydd0_global = zeros(3,1);

for np=1:N_prims
    cart_coord_dmp_params_basic.dt                  = dt;
    cart_coord_dmp_params_basic.n_rfs               = n_rfs;
    cart_coord_dmp_params_basic.c_order             = c_order;
    cart_coord_dmp_params_basic.w                   = dmp_baseline_params.cart_coord{np, 1}.w;
    cart_coord_dmp_params_basic.dG                  = zeros(1,3);   % turn-off scaling in all dimensions
    
    unroll_traj_length                              = size(Ctt_test_prediction_MATLAB_cell{np,1}, 1);
    
    unroll_cart_coord_params_basic.mean_tau         = dt * (unroll_traj_length - 1);
    unroll_cart_coord_params_basic.mean_start_global= y0_global;
    unroll_cart_coord_params_basic.mean_goal_global = dmp_baseline_params.cart_coord{np, 1}.mean_goal_global;
    unroll_cart_coord_params_basic.yd0_global       = yd0_global;
    unroll_cart_coord_params_basic.ydd0_global      = ydd0_global;
    unroll_cart_coord_params_basic.ctraj_local_coordinate_frame_selection   = dmp_baseline_params.cart_coord{np, 1}.ctraj_local_coordinate_frame_selection;
    
    [cart_coord_dmp_params_cell{np, 1}, ...
     cart_coord_dmp_unroll_global_nominal_traj_cell{np, 1}, ...
     cart_coord_dmp_unroll_local_nominal_traj_cell{np, 1}]  = unrollCartPrimitiveOnLocalCoord( cart_coord_dmp_params_basic, ...
                                                                                               unroll_cart_coord_params_basic );
    
    % use the latest state in this primitive to become the initial state of 
    % the next primitive:
    y0_global   = cart_coord_dmp_unroll_global_nominal_traj_cell{np, 1}{1,1}(end,:).';
    yd0_global  = cart_coord_dmp_unroll_global_nominal_traj_cell{np, 1}{2,1}(end,:).';
    ydd0_global = cart_coord_dmp_unroll_global_nominal_traj_cell{np, 1}{3,1}(end,:).';
end

% end of Nominal Unrolling on CartCoordDMP

%% Nominal Unrolling on QuaternionDMP

Quat_dmp_unroll_nominal_traj_cell	= cell(N_prims, 1);

Q0                          = dmp_baseline_params.Quat{1, 1}.fit_mean_Q0;
omega0                      = zeros(3, 1);
omegad0                     = zeros(3, 1);

for np=1:N_prims
    Quat_dmp_params.dt          = dt;
    Quat_dmp_params.n_rfs       = n_rfs;
    Quat_dmp_params.c_order     = c_order;
    Quat_dmp_params.w           = dmp_baseline_params.Quat{np, 1}.w;
    Quat_dmp_params.dG          = zeros(3,1);   % turn-off scaling in all dimensions
    Quat_dmp_params.fit_mean_tau= dmp_baseline_params.Quat{np, 1}.fit_mean_tau;
    Quat_dmp_params.fit_mean_Q0 = dmp_baseline_params.Quat{np, 1}.fit_mean_Q0;
    Quat_dmp_params.fit_mean_QG = dmp_baseline_params.Quat{np, 1}.fit_mean_QG;
    
    unroll_traj_length        	= size(Ctt_test_prediction_MATLAB_cell{np,1}, 1);
    
    % Unrolling based on Dataset (using mean_Q0 and mean_QG)
    unroll_Quat_params.tau          = dt * (unroll_traj_length - 1);
    unroll_Quat_params.traj_length  = unroll_traj_length;
    unroll_Quat_params.start        = Q0;
    unroll_Quat_params.goal         = dmp_baseline_params.Quat{np, 1}.fit_mean_QG;
    unroll_Quat_params.omega0       = omega0;
    unroll_Quat_params.omegad0      = omegad0;
    
    [Quat_dmp_unroll_nominal_traj_cell{np, 1}]  = unrollQuatPrimitive( Quat_dmp_params, ...
                                                                       unroll_Quat_params );
    
    % use the latest state in this primitive to become the initial state of 
    % the next primitive:
    Q0                              = Quat_dmp_unroll_nominal_traj_cell{np, 1}{1,1}(end,:).';
    omega0                          = Quat_dmp_unroll_nominal_traj_cell{np, 1}{4,1}(end,:).';
    omegad0                         = Quat_dmp_unroll_nominal_traj_cell{np, 1}{5,1}(end,:).';
end

% end of Nominal Unrolling on QuaternionDMP

%% Combine Unrollings

pose_unroll_coupled_traj_cell   = cell(N_prims, 1);
pose_unroll_nominal_traj_cell   = cell(N_prims, 1);
unroll_test_data_cell           = cell(N_prims, 1);

for np=1:N_prims
    pose_unroll_coupled_traj_cell{np,1} = [cart_coord_dmp_unroll_global_coupled_traj_cell{np,1}{1,1}, Quat_dmp_unroll_coupled_traj_cell{np,1}{1,1}];
    pose_unroll_nominal_traj_cell{np,1} = [cart_coord_dmp_unroll_global_nominal_traj_cell{np,1}{1,1}, Quat_dmp_unroll_nominal_traj_cell{np,1}{1,1}];
    unroll_test_data_cell{np, 1}        = [unroll_test_data.position{np, 1}(:,1:3), unroll_test_data.orientation{np, 1}(:,1:4)];
end

% end of Combine Unrollings

%% Plotting Results

for np=1:N_prims
    figure;
    for d=1:D
        subplot(D,1,d);
        hold on;
            plot(cart_coord_dmp_unroll_global_nominal_traj_cell{np, 1}{1,1}(:,d), 'r');
            plot(unroll_test_data.position{np, 1}(:,d), 'g');
            plot(cart_coord_dmp_unroll_global_coupled_traj_cell{np, 1}{1,1}(:,d), 'b');
            if (d == 1)
                title(['Position Primitive #', num2str(np)]);
                legend('nominal', 'coupled, ground-truth', 'unrolling with predicted Ct');
            end
        hold off;
    end
    
    figure;
    for d=1:Dq
        subplot(Dq,1,d);
        hold on;
            plot(Quat_dmp_unroll_nominal_traj_cell{np, 1}{1,1}(:,d), 'r');
            plot(unroll_test_data.orientation{np, 1}(:,d), 'g');
            plot(Quat_dmp_unroll_coupled_traj_cell{np, 1}{1,1}(:,d), 'b');
            if (d == 1)
                title(['Orientation (Quaternion) Primitive #', num2str(np)]);
                legend('nominal', 'coupled, ground-truth', 'unrolling with predicted Ct');
            end
        hold off;
    end
    
    figure;
    for d=1:D
        subplot(D,1,d);
        hold on;
            plot(dataset_Ct_tactile_asm.sub_Ct_target{np,setting_no}{trial_no, 1}(:,D+d), 'g');
            plot(Ctt_test_prediction_MATLAB_cell{np,1}(:,D+d), 'b');
            if (d == 1)
                title(['Coupling Term for Orientation (Quaternion) Primitive #', num2str(np)]);
                legend('training/target Ct', 'predicted Ct');
            end
        hold off;
    end
end

% end of Plotting Results