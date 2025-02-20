clear           all;
close           all;
clc;

data_dir        = '../../../../../plot/dmp_coupling/learn_obs_avoid/feature_trajectory/static_obs/single_baseline/';

% exp_type        = 'single_demo/';
exp_type        = 'multi_demo/';

% feat_type       = 'feat0/';
% feat_type       = 'feat1/';

% param_table     = dlmread(strcat(exp_type, feat_type, 'parameter_table.txt'));
% X               = dlmread(strcat(exp_type, feat_type, 'X.txt'));
% Ct_target       = dlmread(strcat(exp_type, feat_type, 'Ct_target.txt'));

param_table     = dlmread(strcat(data_dir, exp_type, 'parameter_table.txt'));
X               = dlmread(strcat(data_dir, exp_type, 'X.txt'));
Ct_target       = dlmread(strcat(data_dir, exp_type, 'Ct_target.txt'));
Ct_fit          = dlmread(strcat(data_dir, exp_type, 'Ct_fit.txt'));
    
% figure;
% hold            on;
% plot(Ct_target(:,1));
% plot(Ct_fit(:,1));
% legend_cfit_idx             = {'Ct\_target', 'Ct\_fit'};
% title('Ct\_fit Evolution (with Ridge Regression)');
% legend(legend_cfit_idx{:});
% hold            off;

% some hack tests:
% param_table     = param_table(:,[26:51,77:102,128:153]);
% X               = X(:,[26:51,77:102,128:153]);

% mean_Ctt        = mean(Ct_target);
% Ctt_temp        = bsxfun(@minus,Ct_target,mean_Ctt);
% Ct_target       = Ctt_temp;

param_table     = param_table';

num_iter        = 40;
debug_interval  = 5;

w_ard           = zeros(size(X,2), size(Ct_target, 2));
for d = 1:3
    [w_ard_d, w_ard_d_idx, cfit_hist, w_hist, log_a_hist]   = ARD(X, Ct_target(:,d), param_table, num_iter, debug_interval, 1);
%     [w_ard_d, w_ard_d_idx, cfit_hist, w_hist, log_a_hist]   = ARD(X, Ct_target(:,d), param_table, num_iter, debug_interval, 0);
    w_ard(w_ard_d_idx, d)                                   = w_ard_d;
    
    figure;
    hold        on;
    plot(Ct_target(:,d));
    legend_cfit_idx             = {'Ct\_target'};
    for k=1:size(cfit_hist,2)
        plot(cfit_hist(:,k));
        legend_cfit_idx{k+1}    = ['iter ', num2str(debug_interval*k)];
    end
    title('Ct\_fit Evolution');
    legend(legend_cfit_idx{:});
    hold        off;
    
    figure;
    hold        on;
    plot(Ct_target(:,d));
    legend_cfit_idx             = {'Ct\_target'};
    plot(cfit_hist(:,end));
    legend_cfit_idx{2}    = ['iter ', num2str(debug_interval*size(cfit_hist,2))];
    title('Ct\_target vs Ct\_fit Final');
    legend(legend_cfit_idx{:});
    hold        off;
    
    figure;
    hold        on;
    legend_w_idx                = {};
    for k=1:size(w_hist,2)
        plot(w_hist(:,k));
        legend_w_idx{k}         = ['iter ', num2str(debug_interval*k)];
    end
    title('w Evolution');
    legend(legend_w_idx{:});
    hold        off;
    
    figure;
    hold        on;
    legend_log_a_idx            = {};
    for k=1:size(log_a_hist,2)
        plot(log_a_hist(:,k));
        legend_log_a_idx{k}     = ['iter ', num2str(debug_interval*k)];
    end
    title('log a Evolution');
    legend(legend_log_a_idx{:});
    hold        off;
    
end
Ct_fit          = X * w_ard;

var_ct          = var(Ct_target, 1);

mse_ard         = mean( (Ct_fit-Ct_target).^2 );
nmse_ard        = mse_ard./var_ct;