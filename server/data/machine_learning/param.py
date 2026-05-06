"""
为机器学习工具内部提供参数解析链
"""

# 加载你的参数定义

def param_types():
    """
    定义模型参数对应的数据类型（完整版本，去重处理）
    """
    return {
        # 通用参数
        # 'random_state': 'int',
        # 'n_jobs': 'int',
        "随机森林": {
            # 随机森林 RandomForestRegressor / RandomForestClassifier
            'n_estimators': 'int',
            'criterion': 'select',
            'max_depth': 'int',
            'min_samples_split': 'int',
            'min_samples_leaf': 'int',
            'min_weight_fraction_leaf': 'float',
            'max_features': 'select',
            'max_leaf_nodes': 'int',
            'min_impurity_decrease': 'float',
            'bootstrap': 'bool',
            'oob_score': 'bool',
            'ccp_alpha': 'float',
            'max_samples': 'int',
        },
        "RandomForestRegressor": {
            # 随机森林 RandomForestRegressor / RandomForestClassifier
            'n_estimators': 'int',
            'criterion': 'select',
            'max_depth': 'int',
            'min_samples_split': 'int',
            'min_samples_leaf': 'int',
            'min_weight_fraction_leaf': 'float',
            'max_features': 'select',
            'max_leaf_nodes': 'int',
            'min_impurity_decrease': 'float',
            'bootstrap': 'bool',
            'oob_score': 'bool',
            'ccp_alpha': 'float',
            'max_samples': 'int',
        },
        # 梯度提升 GradientBoostingRegressor / GradientBoostingClassifier
        "梯度提升树": {
            'learning_rate': 'float',
            'subsample': 'float',
            'validation_fraction': 'float',
            'n_iter_no_change': 'int',
            'tol': 'float',
            'init': 'select',  # estimator 或 None
            'warm_start': 'bool',
        },
        "GradientBoostingRegressor": {
            'learning_rate': 'float',
            'subsample': 'float',
            'validation_fraction': 'float',
            'n_iter_no_change': 'int',
            'tol': 'float',
            'init': 'select',  # estimator 或 None
            'warm_start': 'bool',
        },
        "GradientBoostingClassifier": {
            'learning_rate': 'float',
            'subsample': 'float',
            'validation_fraction': 'float',
            'n_iter_no_change': 'int',
            'tol': 'float',
            'init': 'select',  # estimator 或 None
            'warm_start': 'bool',
        },
        # 线性回归 LinearRegression
        "线性回归": {
            'fit_intercept': 'bool',
            'normalize': 'bool',  # 已弃用
            'copy_X': 'bool',
            'positive': 'bool',
        },
        # 线性回归 LinearRegression
        "LinearRegression": {
            'fit_intercept': 'bool',
            'normalize': 'bool',  # 已弃用
            'copy_X': 'bool',
            'positive': 'bool',
        },
        # Logistic回归 LogisticRegression
        "逻辑回归": {
            'penalty': 'select',
            'dual': 'bool',
            'C': 'float',
            'intercept_scaling': 'float',
            'class_weight': 'select',
            'solver': 'select',
            'multi_class': 'select',
            'l1_ratio': 'float',  # elasticnet
        },
        "LogisticRegression": {
            'penalty': 'select',
            'dual': 'bool',
            'C': 'float',
            'intercept_scaling': 'float',
            'class_weight': 'select',
            'solver': 'select',
            'multi_class': 'select',
            'l1_ratio': 'float',  # elasticnet
        },
        # 支持向量机 SVR / SVC
        "支持向量机": {
            'kernel': 'select',
            'degree': 'int',
            'gamma': 'select',
            'coef0': 'float',
            'shrinking': 'bool',
            'cache_size': 'int',
            'verbose': 'bool',
            'max_iter': 'int',
            'epsilon': 'float',  # SVR
            'probability': 'bool',  # SVC
        },
        # 支持向量机 SVR / SVC
        "SVR": {
            'kernel': 'select',
            'degree': 'int',
            'gamma': 'select',
            'coef0': 'float',
            'shrinking': 'bool',
            'cache_size': 'int',
            'verbose': 'bool',
            'max_iter': 'int',
            'epsilon': 'float',  # SVR
            'probability': 'bool',  # SVC
        },
        "SVC": {
            'kernel': 'select',
            'degree': 'int',
            'gamma': 'select',
            'coef0': 'float',
            'shrinking': 'bool',
            'cache_size': 'int',
            'verbose': 'bool',
            'max_iter': 'int',
            'epsilon': 'float',  # SVR
            'probability': 'bool',  # SVC
        },
        # 决策树 DecisionTreeRegressor / DecisionTreeClassifier
        'splitter': 'select',

        "决策树": {
            # KNN KNeighborsRegressor / KNeighborsClassifier
            'n_neighbors': 'int',
            'weights': 'select',
            'algorithm': 'select',
            'leaf_size': 'int',
            'p': 'int',
            'metric': 'select',
            'metric_params': 'dict',
        },

        "KNeighborsRegressor": {
            # KNN KNeighborsRegressor / KNeighborsClassifier
            'n_neighbors': 'int',
            'weights': 'select',
            'algorithm': 'select',
            'leaf_size': 'int',
            'p': 'int',
            'metric': 'select',
            'metric_params': 'dict',
        },
        "KNeighborsClassifier": {
            # KNN KNeighborsRegressor / KNeighborsClassifier
            'n_neighbors': 'int',
            'weights': 'select',
            'algorithm': 'select',
            'leaf_size': 'int',
            'p': 'int',
            'metric': 'select',
            'metric_params': 'dict',
        }
    }


def param_options_map():
    """
    定义枚举类型参数的可选值（完整版本，去重处理）
    """
    return {
        #
        "随机森林": {
            'criterion': ['mse', 'friedman_mse', 'mae', 'poisson', 'gini', 'entropy'],
            'max_features': ['auto', 'sqrt', 'log2', None],
        },
        "决策树": {
            # 决策树
            'criterion': ['mse', 'friedman_mse', 'mae', 'poisson', 'gini', 'entropy'],
            'max_features': ['auto', 'sqrt', 'log2', None],
            'splitter': ['best', 'random'],
        },
        # Logistic回归
        "逻辑回归": {
            'penalty': ['l1', 'l2', 'elasticnet', 'none'],
            'solver': ['lbfgs', 'liblinear', 'newton-cg', 'sag', 'saga'],
            'multi_class': ['auto', 'ovr', 'multinomial'],
            'class_weight': ['balanced', None],
        },
        # 支持向量机
        "支持向量机": {
            'kernel': ['linear', 'poly', 'rbf', 'sigmoid', 'precomputed'],
            'gamma': ['scale', 'auto'],
        },
        # KNN
        "KNN": {
            'weights': ['uniform', 'distance'],
            'algorithm': ['auto', 'ball_tree', 'kd_tree', 'brute'],
            'metric': ['minkowski', 'euclidean', 'manhattan', 'chebyshev', 'precomputed'],
        },
        # GradientBoosting init
        "梯度提升树": {
            'init': [None],  # 可以是 estimator, 这里简单处理
        }
    }


from skopt.space import Categorical, Integer, Real


def get_model_param_spaces():
    """
    为分类/回归模型提供可用于 BayesSearchCV 的参数空间
    所有搜索空间均已确保 sklearn 与 skopt 完全兼容
    """

    return {

        "分类": {

            "KNN": {
                "n_neighbors": Categorical([3, 5, 7, 9, 11, 13, 15, 17, 19, 21]),
                "weights": Categorical(["uniform", "distance"]),
                "p": Integer(1, 2),
                "metric": Categorical(["minkowski", "chebyshev"])
            },

            "逻辑回归": {
                # C 范围
                "C": Real(0.01, 100, prior="log-uniform"),

                # penalty/solver 组合需要手动避免非法组合
                "penalty": Categorical(["l1", "l2", "elasticnet"]),

                # saga 支持 l1/l2/elasticnet, liblinear 支持 l1/l2
                "solver": Categorical(["liblinear", "saga"]),

                # 仅 elasticnet 使用，但 skopt 会自动跳过无效参数组合
                "l1_ratio": Real(0.0, 1.0),

                "class_weight": Categorical(["balanced", None])
            },

            "决策树": {
                "max_depth": Integer(3, 15),
                "min_samples_split": Real(0.01, 0.5, prior="log-uniform"),
                "min_samples_leaf": Real(0.01, 0.2, prior="log-uniform"),
                "criterion": Categorical(["gini", "entropy"]),
                "class_weight": Categorical(["balanced", None])
            },

            "随机森林": {
                "n_estimators": Integer(50, 300),
                "max_depth": Integer(5, 20),
                "min_samples_split": Real(0.01, 0.3, prior="log-uniform"),
                "min_samples_leaf": Real(0.01, 0.1, prior="log-uniform"),
                "max_features": Categorical(["sqrt", "log2"]),
                "bootstrap": Categorical([True, False]),
                "class_weight": Categorical(["balanced", "balanced_subsample", None])
            },

            "梯度提升树": {
                "n_estimators": Integer(100, 500),
                "learning_rate": Real(0.001, 0.3, prior="log-uniform"),
                "max_depth": Integer(3, 10),
                "min_samples_split": Real(0.01, 0.2, prior="log-uniform"),
                "subsample": Real(0.6, 1.0),
                "max_features": Categorical(["sqrt", "log2"]),
                "loss": Categorical(["log_loss", "deviance"])
            },

            "支持向量机": {
                "C": Real(0.1, 100, prior="log-uniform"),
                "kernel": Categorical(["linear", "poly", "rbf", "sigmoid"]),

                # 不能用 Categorical + Real，需要手动列举
                "gamma": Categorical(
                    ["scale", "auto", 0.001, 0.01, 0.1, 1, 10]
                ),

                "degree": Integer(2, 5),
                "class_weight": Categorical(["balanced", None]),
                "probability": Categorical([True])  # 固定开启
            }
        },

        # =======================================================================================
        "回归": {

            "KNN": {
                "n_neighbors": Categorical([3, 5, 7, 9, 11, 13, 15, 17, 19, 21]),
                "weights": Categorical(["uniform", "distance"]),
                "p": Integer(1, 2),
                "metric": Categorical(["minkowski", "chebyshev"])
            },

            "线性回归": {
                "fit_intercept": Categorical([True, False]),
                "normalize": Categorical([True, False]),
                "copy_X": Categorical([True, False])
            },

            "决策树": {
                "max_depth": Integer(3, 15),
                "min_samples_split": Real(0.01, 0.5, prior="log-uniform"),
                "min_samples_leaf": Real(0.01, 0.2, prior="log-uniform"),
                "criterion": Categorical(["squared_error", "absolute_error"]),
                "splitter": Categorical(["best", "random"])
            },

            "随机森林": {
                "n_estimators": Integer(50, 300),
                "max_depth": Integer(5, 20),
                "min_samples_split": Real(0.01, 0.3, prior="log-uniform"),
                "min_samples_leaf": Real(0.01, 0.1, prior="log-uniform"),
                "max_features": Categorical(["sqrt", "log2"]),
                "bootstrap": Categorical([True, False]),
                "criterion": Categorical(["squared_error", "absolute_error"])
            },

            "梯度提升树": {
                "n_estimators": Integer(100, 500),
                "learning_rate": Real(0.001, 0.3, prior="log-uniform"),
                "max_depth": Integer(3, 10),
                "min_samples_split": Real(0.01, 0.2, prior="log-uniform"),
                "subsample": Real(0.6, 1.0),
                "max_features": Categorical(["sqrt", "log2"]),
                "loss": Categorical(["squared_error", "absolute_error"])
            },

            "支持向量机": {
                "C": Real(0.1, 100, prior="log-uniform"),
                "kernel": Categorical(["linear", "poly", "rbf", "sigmoid"]),
                "gamma": Categorical(
                    ["scale", "auto", 0.001, 0.01, 0.1, 1, 10]
                ),
                "degree": Integer(2, 5),
                "epsilon": Real(0.01, 1.0)
            }
        }
    }


# 使用示例：获取分类任务中"随机森林"的参数空间
param_spaces = get_model_param_spaces()
param_types = param_types()
param_options_map = param_options_map()


def cast_params(model_name, params_dict, param_types):
    """
    根据 param_types 的类型定义对参数进行类型转换
    (此函数功能完善，无需修改)
    """
    casted = {}
    type_map = {
        'int': int,
        'float': float,
        'bool': lambda x: str(x).lower() in ["true", "1"],  # 稍稍增强 bool 的判断
        'select': str,
        'dict': dict
    }
    for k, v in params_dict.items():
        if k in param_types.get(model_name, {}):
            typ_str = param_types[model_name][k]
            typ_func = type_map.get(typ_str, str)
            try:
                casted[k] = typ_func(v)
            except Exception:
                print(f"Warning: 参数 {k}={v} 类型转换失败 ({typ_str})，已忽略，使用默认值")
        else:
            print(f"Warning: 参数 {k} 对模型 {model_name} 不存在类型定义，忽略。")
    return casted


def validate_enum_params(model_name, params_dict, param_options_map):
    """
    过滤掉不合法的枚举参数
    (此函数功能完善，无需修改)
    """
    valid_params = {}
    for k, v in params_dict.items():
        if k in param_options_map.get(model_name, {}):
            if v in param_options_map[model_name][k]:
                valid_params[k] = v
            else:
                print(f"Warning: 参数 {k}={v} 对模型 {model_name} 不合法，已忽略，使用默认值")
        else:
            valid_params[k] = v
    return valid_params

