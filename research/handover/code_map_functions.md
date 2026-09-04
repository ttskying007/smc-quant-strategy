# 代码函数地图（自动提取）

- 覆盖 Python 文件: 1642

## hermes\scripts\analysis_page.py
- `build_analysis_page()` — 

## hermes\scripts\analyze_baseline.py

## hermes\scripts\analyze_crawl.py

## hermes\scripts\analyze_v13.py

## hermes\scripts\analyze_v14.py

## hermes\scripts\analyze_v14_full.py

## hermes\scripts\apply_fix.py

## hermes\scripts\audit_v11.py

## hermes\scripts\auto_iter_v61.py
- `evaluate_quick(params, stocks, n)` — Quick evaluation on n stocks
- `run_auto_iter(target_iterations)` — Main auto-iteration loop

## hermes\scripts\auto_iter_v7.py
- `load_candidates()` — 从V4/V6结果加载候选股票
- `perturb_params(params, intensity)` — 小幅扰动参数
- `full_evaluate(params, bars_dict, verbose)` — 全量评估指定参数
- `run_auto_iter_v7(target_iters, n_stocks, parallel)` — Run V7 auto-iteration

## hermes\scripts\backtest_v116_full.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `find_nearest_swing_low(ohlcv, end_idx, lookback)` — 
- `find_nearest_swing_high(ohlcv, end_idx, lookback)` — 
- `calc_swing_sltp(ohlcv, end_idx, entry_price)` — 
- `get_entry_signal_info(seq_result)` — 
- `process_stock(symbol)` — 
- `main()` — 

## hermes\scripts\backtest_v11_final.py

## hermes\scripts\backtest_v12.py
- `load_ohlcv(symbol)` — 加载日线缓存
- `find_swing_points(ohlcv, lookback)` — 找出摆动高点和低点
- `find_swing_near_signal(sig_idx, ohlcv, swing_highs, swing_lows, max_dist)` — 信号附近是否有摆动点
- `score_signal_quality(sig, ohlcv, swing_highs, swing_lows)` — 综合信号质量评分 (0-100)
- `analyze_signal_entry(ohlcv, all_signals, swing_highs, swing_lows, params)` — 版v2 — 每个信号独立检测入场机会
- `scan_params_for_stock(ohlcv, all_signals, swing_highs, swing_lows, base_params, phase)` — 扫描SL/TP参数组合, 找最优
- `backtest_stock(ohlcv, symbol, use_param_scan)` — 单股票全流程回测
- `main()` — 

## hermes\scripts\backtest_v13.py
- `short_trend(ohlcv, idx, lookback)` — 
- `load_ohlcv(symbol)` — 
- `analyze_at_point(ohlcv, all_signals, end_idx, params)` — 
- `simulate_trades(ohlcv, all_signals, params)` — 
- `backtest_single_stock(symbol)` — 单股票回测 — 供并行调用
- `main()` — 

## hermes\scripts\backtest_v14.py
- `load_ohlcv(symbol)` — 
- `find_swing_points(ohlcv, lookback)` — 
- `score_signal_quality(first_sig, ohlcv, swing_highs, swing_lows)` — 信号质量评分 (0-100), 宽松版
- `find_entry_points(ohlcv, all_signals, swing_highs, swing_lows, base_params)` — 一次检测所有入场点, 返回entry列表供后续参数模拟
- `simulate_exits(ohlcv, entries, sl_pct, tp_pct)` — 对给定的SL/TP, 模拟所有entry的退出结果
- `backtest_stock(args)` — 单股票 — 入场检测1次 + 参数扫描10次模拟
- `main()` — 

## hermes\scripts\build_skill_index.py

## hermes\scripts\check_5000.py

## hermes\scripts\check_cache.py

## hermes\scripts\check_cache2.py

## hermes\scripts\check_chrome_cookies.py

## hermes\scripts\check_code.py

## hermes\scripts\check_format.py

## hermes\scripts\check_hubble_api.py

## hermes\scripts\check_intervals.py

## hermes\scripts\check_json_struct.py

## hermes\scripts\check_keyring_tools.py

## hermes\scripts\check_pool.py

## hermes\scripts\check_v4.py

## hermes\scripts\chrome_headless_login.py

## hermes\scripts\clash_sub_hunter.py
- `xcrawl_search(query, limit, tbs)` — Search via xcrawl API.
- `fetch_url(url, timeout)` — Download a URL with timeout.
- `test_proxy_yaml(data)` — Quick check if content looks like a valid Clash config with proxies.
- `main()` — 

## hermes\scripts\compare_all.py

## hermes\scripts\daily_crawler.py
- `fetch(url, params, json_fmt, timeout)` — 

## hermes\scripts\daily_multi_source_crawler.py
- `retry_request(url, params, json_fmt, timeout, max_tries)` — 增强版请求重试: 先走代理, 失败后直连, 每次换策略
- `retry_urllib(url, headers, timeout, max_tries)` — urllib 请求重试: 先直连, 后代理(用requests, 修复urllib ProxyHandler context兼容问题)
- `load_config()` — 
- `save_config(cfg)` — 写回配置（更新查询统计）
- `verify_text(text, direction_cfg)` — 返回: ('precise', matched_word) | ('false', matched_exclude) | ('uncertain', None)
- `load_x_cookies()` — 
- `fetch_bing_for_query(direction_id, query_obj)` — 
- `fetch_github_for_query(direction_id, query_obj)` — 
- `fetch_hn_for_query(direction_id, query_obj)` — 
- `fetch_brave_for_query(direction_id, query_obj)` — Fetch Brave Search results (stands in for Google). Reddit content appears naturally in res
- `fetch_google_news_for_query(direction_id, query_obj)` — Fetch Google News RSS (English query only, returns 60-100+ items per query).
- `fetch_url(url, params, json_fmt, timeout, use_proxy)` — 通用HTTP请求: 3次重试 + proxy/direct fallback。
- `ensure_l30d_env()` — Load SCRAPECREATORS_API_KEY from env file if not already set.
- `fetch_via_last30days(direction_id, query_obj)` — 调用 last30days 引擎研究一个话题，返回 crawler 格式的 items.
- `fetch_via_hn_algolia(direction_id, query_obj)` — Fetch Hacker News stories via Algolia API. Free, no API key needed, works from GFW.
- `analyze_query(query_id, direction_cfg, stats)` — 返回建议文本字符串

## hermes\scripts\debug_backtest.py

## hermes\scripts\debug_cache.py

## hermes\scripts\debug_cache2.py
- `load_bars_from_cache(symbol, limit)` — 

## hermes\scripts\debug_int.py

## hermes\scripts\debug_perf.py

## hermes\scripts\debug_swing.py

## hermes\scripts\debug_t.py

## hermes\scripts\debug_twikit.py

## hermes\scripts\decrypt_chrome_cookies.py

## hermes\scripts\deep_debug.py

## hermes\scripts\diagnose_silver.py
- `analyze()` — 

## hermes\scripts\diagnose_v11.py

## hermes\scripts\diagnose_v11_stocks.py

## hermes\scripts\diagnose_v7.py

## hermes\scripts\download_60min_cache.py
- `download_60min(symbol)` — Download and cache 60min data for a symbol
- `main()` — 

## hermes\scripts\download_etf_cache.py

## hermes\scripts\etf_signal_scanner.py
- `get_tencent_kline(symbol, period, count)` — 获取Tencent K线数据.
- `parse_tencent_kline(raw, period)` — Parse Tencent K-line JSON to standard format.
- `load_or_fetch_tencent(symbol, tencent_code, period)` — Load from cache or fetch from Tencent API.
- `detect_signals(ohlcv, symbol, label)` — Run V11 signal detection on OHLCV data.
- `main()` — 

## hermes\scripts\examine_local_state.py

## hermes\scripts\extract_chrome_cookies.py
- `get_encryption_key()` — Get the Chrome encryption key from Local State.
- `get_cookies_v10()` — Chrome v1.0 encryption - plaintext.
- `decrypt_value_v11(encrypted_value, key)` — Decrypt Chrome v1.1+ encrypted cookie value.
- `get_linux_key_from_local_state()` — Get the raw decryption key from Local State.
- `try_get_chrome_key_from_query()` — Try to query the Chromium keyring secret.
- `get_cookies_v11()` — Chrome v1.1+ encryption - AES-256-GCM.
- `read_cookies_directly()` — Try to read cookies from the SQLite database - first approach.

## hermes\scripts\final_report_v4.py

## hermes\scripts\find_chrome_key.py

## hermes\scripts\find_int.py

## hermes\scripts\fix_v14_render.py

## hermes\scripts\gen_v4_signals.py
- `load_bars(symbol, limit)` — 

## hermes\scripts\gen_v4_signals_v3.py
- `load_bars(symbol)` — 
- `fmt_time(val)` — 

## hermes\scripts\gen_v61_signals.py

## hermes\scripts\gen_v62_signals.py

## hermes\scripts\generate_signal_details.py
- `get_klines_detailed(symbol, limit)` — 获取K线，返回带时间格式的数据
- `extract_signal_details(code, name)` — 对单只股票提取所有信号详情
- `format_signal_report(detail)` — 格式化单只股票的信号报告文本
- `generate_reports(signal_stocks, top_n)` — 生成所有信号的详情
- `main()` — 
- `fmt_time(idx)` — 
- `fmt_price(p)` — 

## hermes\scripts\generate_signal_details_v2.py
- `load_bars_from_cache(symbol, limit)` — 从本地缓存读取K线
- `extract_signal_details(code, name)` — 提取信号详情 (从本地缓存)
- `process_batch(stock_list, start_idx, batch_size)` — 分批处理
- `main()` — 
- `fmt_time(idx)` — 

## hermes\scripts\list_all_secrets.py

## hermes\scripts\manage_interests.py
- `load_interests()` — 
- `save_interests(interests)` — 
- `list_interests(interests)` — 

## hermes\scripts\merge_v116.py

## hermes\scripts\merge_v13.py

## hermes\scripts\monitor_page.py
- `load_monitor_data()` — 
- `build_combo_matrix(picks, combo_stats)` — Render CTX × POI signal matrix as heatmap table
- `build_l2_perf_table()` — Load L2 backtest results and render performance table
- `build_monitor_page()` — 

## hermes\scripts\monkey_patch_twikit.py
- `apply_patch()` — 
- `patched___init__(self)` — 
- `patched_gen_id(self, method, path, response, key, animation_key)` — 

## hermes\scripts\multi_tf_v38_test.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `detect_daily_only(ohlcv, symbol)` — 纯日线V38.4检测
- `detect_multi_tf(symbol, daily_ohlcv, ohlcv_60min)` — V38.4 + 60min Multi-TF检测
- `main()` — 

## hermes\scripts\optimize_multi_param.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `run_single_param(ohlcv, all_signals, symbol, params_dict)` — 用一组参数运行回测
- `optimize_stock(ohlcv, all_signals, symbol, n_iterations, n_samples, n_elite)` — 多参数迭代优化
- `main()` — 

## hermes\scripts\playwright_copy_profile.py

## hermes\scripts\playwright_x_scraper.py

## hermes\scripts\proxy_guardian.py
- `log(msg)` — 
- `check_process()` — 检查mihomo进程是否存在
- `check_http_proxy()` — 检查代理端口是否响应（仅HTTP，HTTPS失败不算致命）
- `check_api()` — 检查Clash API是否响应
- `restart_proxy()` — 重启代理
- `cleanup()` — 
- `main()` — 

## hermes\scripts\proxy_guardian_v2.py
- `log(msg)` — 日志
- `rotate()` — 日志轮转
- `save_status(status)` — 保存状态供外部读取
- `check_process()` — 检查mihomo进程
- `check_http_proxy()` — 检查代理HTTP端口
- `check_internet_connectivity()` — 实际连通性检测
- `check_api()` — 检查Clash API
- `get_traffic()` — 获取流量信息 (仅用于健康报告)
- `restart_proxy()` — 重启代理 (带降级)
- `single_check()` — 单次检查 (用于cron调用)
- `cleanup()` — 
- `main()` — 

## hermes\scripts\proxy_guardian_v3.py
- `log(msg)` — 
- `rotate()` — 
- `save_status(status)` — 
- `check_process()` — 
- `check_api()` — 
- `check_http_proxy()` — 
- `check_internet()` — 
- `kill_existing()` — 
- `find_working_config()` — 找到可用的配置文件
- `ensure_mihomo_binary()` — 确保mihomo二进制可用
- `try_alternate_port_start()` — 尝试用不同的端口启动 (如果7890被占用)
- `restart_proxy()` — 
- `single_check()` — 
- `show_status()` — 
- `cleanup()` — 
- `main()` — 

## hermes\scripts\proxy_guardian_v4.py
- `log(msg)` — 
- `save_status(status)` — 
- `load_status()` — 
- `check_process()` — 检测1: 进程存活
- `check_port(port)` — 检测2: 端口监听
- `check_api()` — 检测3: 控制API存活
- `check_connectivity()` — 检测4: HTTP连通性 (4个URL轮流)
- `check_dns()` — 检测5: DNS解析
- `kill_all_mihomo()` — 强制杀死所有mihomo进程
- `start_mihomo(config_path)` — 启动mihomo
- `try_update_config()` — 尝试更新订阅 (调用clash_sub_hunter.py)
- `single_check()` — 单次检查
- `main_loop()` — 守护进程

## hermes\scripts\proxy_guardian_v6.py
- `check_process()` — 检查1: mihomo进程是否存在
- `check_api()` — 检查2: mihomo API端口9090
- `check_http_connectivity()` — 检查3: 通过代理访问外网
- `kill_proxy()` — 杀掉所有mihomo进程
- `start_proxy()` — 启动mihomo代理
- `restart_proxy()` — 完整的重启流程
- `write_status(ok, proc_msg, api_msg, latency, restart_count, consecutive_failures)` — 写入状态JSON到所有SMC版本目录
- `main()` — 

## hermes\scripts\proxy_guardian_v7.py
- `query_mihomo_api(endpoint)` — 查询mihomo API
- `check_proxy_process()` — 检查mihomo进程
- `check_api()` — 检查mihomo API是否可达
- `check_internet()` — 检查互联网连通性 — 区分GFW和纯网络
- `get_proxy_groups()` — 获取mihomo代理组和节点
- `test_node_delay(group, node_name)` — 测试单个节点延迟
- `switch_proxy_node(group_name, node_name)` — 切换代理组到指定节点
- `find_best_node()` — 自动寻找最优节点
- `kill_mihomo()` — 杀掉所有mihomo进程
- `check_config_exists()` — 检查配置文件
- `start_mihomo(config_path)` — 启动mihomo
- `save_proxy_status()` — 写状态JSON供WebUI
- `main_loop()` — 主循环

## hermes\scripts\proxy_guardian_v8.py
- 类: ProxyGuardianV8
- `show_status()` — 打印当前状态
- `single_check()` — 
- `_handle_signal(self, signum, frame)` — 
- `check_process(self)` — 检测mihomo进程
- `check_port(self)` — 检测7890端口
- `check_http(self, url, timeout)` — 通过代理检测HTTP连通性, 返回 (ok, latency_ms)
- `check_connectivity(self)` — 三层连通性检测: gstatic → google → baidu (区分GFW vs 本地网络)
- `query_mihomo(self, endpoint)` — 调用mihomo API
- `get_proxy_groups(self)` — 获取代理组和当前选中节点, 返回 (name, now, all_nodes)
- `switch_node(self, group_name, target_node)` — 通过API切换到指定节点或延迟最低节点
- `restart_mihomo(self)` — 重启mihomo进程
- `get_node_count(self)` — 获取节点存活/总数
- `write_status(self, state)` — 写入状态JSON到所有目录
- `run_once(self)` — 执行一轮完整检测
- `run(self)` — 主循环

## hermes\scripts\proxy_guardian_v8_fixed.py
- 类: ProxyGuardianV8Fixed
- `show_status()` — 打印当前状态
- `single_check()` — 
- `_handle_signal(self, signum, frame)` — 
- `_get_current_config(self)` — 自动检测当前运行的mihomo配置路径
- `check_process(self)` — 检测mihomo进程
- `check_port(self)` — 检测7890端口
- `check_http(self, url, timeout)` — 通过代理检测HTTP连通性, 返回 (ok, latency_ms)
- `check_connectivity(self)` — 三层连通性检测: gstatic -> google -> baidu
- `query_mihomo(self, endpoint)` — 调用mihomo API
- `get_proxy_groups(self)` — 获取代理组和当前选中节点, 返回 (name, now, all_nodes)
- `get_node_delays(self)` — 获取所有代理节点的延迟信息
- `switch_node(self, group_name)` — 通过API切换到延迟最低的可用节点 — 不会中断API接口!
- `restart_mihomo(self)` — 优雅重启mihomo — 使用正确的配置路径
- `get_node_count(self)` — 获取节点存活/总数
- `write_status(self, state)` — 写入状态JSON
- `run_once(self)` — 执行一轮完整检测
- `run(self)` — 主循环

## hermes\scripts\quick_check.py

## hermes\scripts\restore_v45_5_event_page.py
- `load_json(path, default)` — 
- `f(v, default)` — 
- `i(v, default)` — 
- `date_from_trade(t, key)` — 
- `event(event_id, t, event_type, idx_key, date_key)` — 
- `build_events(trades)` — 
- `build_setups(trades)` — 
- `normalize_pick(p, active)` — 
- `main()` — 

## hermes\scripts\rolling_backtest_v4.py
- `run_backtest_v4(symbol, params_override)` — 

## hermes\scripts\rolling_backtest_v5.py
- `run_v5(symbol, params_override)` — 

## hermes\scripts\run_ga_v61.py

## hermes\scripts\run_ga_v61_v2.py
- `random_params()` — 
- `crossover(p1, p2)` — 
- `mutate(p)` — 
- `evaluate_params(params, bars_dict)` — Evaluate params on all stocks — returns IS and OOS scores

## hermes\scripts\run_ga_v61_v3.py
- `random_params()` — 
- `crossover(p1, p2)` — 
- `mutate(p)` — 
- `multi_objective_score(is_wr, is_n, oos_wr, oos_n, is_pf, oos_pf)` — Multi-objective: WR dominance with trade count
- `evaluate(params)` — 

## hermes\scripts\run_ga_v61_v4.py
- `rand_param()` — Generate random params respecting constraint tp >= sl + MIN_DIFF
- `mutate(p)` — 
- `crossover(p1, p2)` — 
- `evaluate(params, stocks)` — Evaluate param set on 60% of stocks (IS), returns score and full results
- `genetic_search(generations, pop_size, stocks)` — 

## hermes\scripts\run_optimizer.py
- `main()` — 

## hermes\scripts\skill_discovery_pipeline.py
- `load_latest_crawl()` — 加载最新爬虫结果
- `load_dedup_db()` — 加载去重数据库
- `save_dedup_db(db)` — 保存去重数据库
- `filter_candidates(crawl_data)` — 从爬虫结果中过滤出候选
- `url_hash(url)` — 
- `jaccard_similarity(s1, s2)` — 集合Jaccard相似度
- `normalize_repo_name(name)` — 标准化GitHub仓库名
- `check_duplicate(item, db)` — 三层去重,返回(是否重复, 原因)
- `score_source_credibility(item)` — 维度1: 源可信度
- `score_community(item)` — 维度2: 社区验证 — stars/points
- `score_actionability(item)` — 维度3: 可操作性 — 能装成skill吗?
- `score_novelty(item, db)` — 维度4: 新颖度
- `score_relevance(item)` — 维度5: 主题相关性
- `compute_score(item, db)` — 综合五维评分
- `extract_github_info(item)` — 从item中提取GitHub仓库信息
- `install_from_github(gh_info, item, score_info)` — 从GitHub安装一个工具为skill
- `generate_skill_md(gh_info, item, score_info, safe_name, skill_dir, has_readme)` — 生成标准的SKILL.md
- `verify_skill(skill_dir, safe_name, gh_info, is_python, install_ok)` — 验证安装效果
- `main()` — 

## hermes\scripts\skill_hunter.py
- `xcrawl_search(query, limit, tbs, timeout)` — Search via curl subprocess — urllib.request is broken for XCrawl
- `main()` — 

## hermes\scripts\smc_api_lite.py
- 类: H
- `lj(path, default)` — 
- `proxy_status()` — 
- `do_GET(self)` — 
- `r(self, data, code)` — 
- `log_message(self)` — 

## hermes\scripts\smc_api_v2.py
- `safe_read_json(path)` — 
- `fetch_hubble(endpoint, timeout)` — 
- `get_cached_kline(symbol, period, count)` — Get kline data with Hubble → file cache fallback
- `normalize_kline_data(data)` — Normalize to [{open, high, low, close, volume, timestamp}]
- `klines_to_echarts(klines)` — Convert kline data to ECharts format with MA
- `get_proxy_status()` — 
- `get_proxy_logs(lines)` — 
- `build_status_payload()` — Build combined status payload for WebSocket push
- `start_optimizer(iters, stocks, tighten, seed)` — 
- `stop_optimizer()` — 

## hermes\scripts\smc_auto_optimizer.py
- 类: ParameterGenerator, SignalMutator, SMCOptimizer
- `compute_objective_score(sharpe, profit_factor, total_trades, win_rate, max_dd)` — 目标评分函数 v4 (修复版):
- `evaluate_params(params, symbol_list, strategy, max_stocks)` — 评估一组参数的表现
- `main()` — 
- `get_default_params(self)` — 
- `get_grid_iterations(self)` — 生成所有网格参数组合（有限步进）
- `get_genetic_params(self, mutation_rate, crossover_rate)` — 遗传算法生成下一组参数
- `get_random_params(self)` — 随机参数（用于初始探索）
- `get_bayesian_params(self)` — 基于历史的最佳参数区域采样
- `next_params(self, mode)` — 生成下一组参数
- `record_result(self, params, score)` — 记录一次迭代结果
- `mutate(self)` — 随机变异一个检测器
- `apply_to_detection(self, bars, params)` — 应用当前变异配置到信号检测
- `_detect_fvg_mutated(self, klines, params, variant)` — 变异版FVG检测
- `_detect_sweep_mutated(self, klines, params, variant)` — 变异版Sweep检测
- `_detect_ob_mutated(self, klines, params, variant)` — 变异版OB检测
- `log_performance(self, mutation_key, score)` — 
- `get_best_mutation(self, detector)` — 
- `load_stock_list(self)` — 加载A股股票列表
- `check_proxy(self)` — 检查代理是否存活，失败则尝试重启
- `run_single_iteration(self, params, strategy)` — 运行一次迭代: 回测 -> 评分
- `run_iteration(self, mode)` — 完整的一次迭代流程
- `save_state(self)` — 保存当前状态
- `load_state(self)` — 从上次中断恢复
- `print_progress(self, result, is_best)` — 打印进度
- `run(self, iterations, mode, resume)` — 主运行循环

## hermes\scripts\smc_batch_v3.py

## hermes\scripts\smc_batch_v33.py
- `calc_wr(t)` — 

## hermes\scripts\smc_daily_scan.py

## hermes\scripts\smc_dashboard_v3.py
- 类: Handler
- `stats_html()` — 
- `do_GET(self)` — 
- `log_message(self)` — 

## hermes\scripts\smc_dashboard_v4.py
- 类: Handler
- `dashboard_html()` — Generate V4 interactive dashboard HTML using only stock_results + summary
- `do_GET(self)` — 
- `log_message(self)` — 

## hermes\scripts\smc_engine_v3.py
- `multi_signal_resonance(bars, params)` — 多信号共振检测: FVG+Sweep+OB+CHOCH+OTE五维确认
- `smc_structural_sl_tp(bars, direction, entry_idx, params)` — 基于SMC流动性结构的止损止盈（简化版）
- `multi_tf_alignment(daily_bars, weekly_bars, h4_bars, h1_bars)` — 多TF方向一致性检查
- `detect_high_winrate_entries(bars)` — 高胜率入场信号检测
- `backtest_v3_high_winrate(bars, only_long)` — V3回测引擎: 只用高胜率信号
- `evaluate_v3_trades(trades, name)` — 评估V3回测结果

## hermes\scripts\smc_engine_v3_1.py
- `detect_fvg_multi_threshold(bars)` — 多阈值FVG检测: 在3个不同阈值下检测, 合并结果
- `detect_sweep_multi_lookback(bars)` — 多回看周期Sweep检测
- `detect_high_winrate_entries_v3_1(bars)` — V3.1 高胜率入场: 多阈值FVG + 多回看Sweep + 宽松CHOCH
- `backtest_v3_1(bars, only_long)` — V3.1 回测
- `evaluate(trades, name)` — 评估

## hermes\scripts\smc_engine_v3_2.py
- `detect_fvg_multi(bars)` — 4阈值FVG检测
- `detect_sweep_multi(bars)` — 5回看周期Sweep
- `detect_choch_wide(bars)` — 多窗口CHOCH检测 — 用多个lookback
- `detect_entries_v3_2(bars)` — V3.2 入口检测 — 多阈值共振 + 时间加权
- `backtest_v3_2(bars, only_long)` — 
- `evaluate_v3_2(trades, name)` — 

## hermes\scripts\smc_engine_v3_3.py
- `calc_atr(bars, period)` — 
- `detect_fvg_multi_full(bars, thresholds)` — 全量FVG检测: 4个阈值+全范围
- `detect_sweep_multi_full(bars)` — 全量Sweep: 5回看周期
- `detect_entries_v3_3(bars)` — V3.3 入口检测 — 自适应信号倍增
- `backtest_v3_3(bars, mode)` — V3.3 回测
- `evaluate(trades, name)` — 结果评估
- `dedup(entries)` — 

## hermes\scripts\smc_engine_v3_4.py
- `detect_fvg_multi_v34(bars)` — 5阈值FVG检测
- `detect_entries_v3_4(bars)` — V3.4 入口检测 — 平衡版
- `backtest_v3_4(bars, only_long)` — V3.4 回测
- `evaluate(trades, name)` — 

## hermes\scripts\smc_engine_v3_5.py
- `backtest_v3_5(bars, only_long)` — V3.5: V3.2核心 + score门槛从3.0降至2.5
- `evaluate(trades, name)` — 

## hermes\scripts\smc_engine_v4.py
- `fetch_hubble(url, timeout)` — 
- `get_klines(symbol, interval, limit)` — 
- `get_stock_list()` — 
- `calc_atr(klines, period)` — 
- `find_swing_highs(klines, left, right)` — 
- `find_swing_lows(klines, left, right)` — 
- `detect_fvg_standard(bars, threshold)` — 标准FVG: 基于3K线缺口
- `detect_fvg_wide(bars, threshold)` — 宽幅FVG: 低阈值, 捕获更多FVG
- `detect_fvg_merge(bars, threshold, max_gap)` — 连续合并FVG: 相邻FVG合并为一个区域
- `detect_sweep_precise(bars, lookback, wick_min, body_min_pct)` — 精准Sweep检测:
- `detect_pivot_highs(bars, left, right)` — 
- `detect_pivot_lows(bars, left, right)` — 
- `detect_choch_v4(bars)` — V4 CHOCH: LL+Break或HH+Break + V2 fallback
- `detect_ob_v4(bars, fvg_list)` — V4 OB: 只在FVG重叠时保留
- `calc_bpr_v4(fvg_list, max_idx)` — V4 BPR: 仅最近30根的FVG对, 取strength最大的
- `get_volatility_profile(bars)` — 返回股票的波动率画像
- `get_adaptive_params(vol_profile)` — 基于波动率画像返回自适应参数
- `_ensure_time(bars)` — 
- `detect_entries_v4(bars, params)` — 
- `simulate_entry(entry, bars)` — 模拟一笔entry
- `backtest_v4(bars, mode, params)` — 
- `evaluate(trades, name)` — 
- `compute_v4_score(trades)` — V4评分: 侧重WR和PF, 同时考虑样本量
- `merge_group(sigs)` — 

## hermes\scripts\smc_engine_v5.py
- `calc_atr(klines, period)` — 
- `calc_ema(data, period)` — 
- `calc_rsi(bars, period)` — 
- `get_volatility_profile_v5(bars)` — V5波动率画像 — 更精细的分类
- `detect_fvg_multi_scale(bars, params)` — 多尺度FVG检测: 3种阈值 × 动态窗口
- `detect_sweep_v5(bars, params)` — V5 Sweep检测: 精准长影线猎杀
- `detect_ob_v5(bars, params, fvg_list)` — V5 OB检测: 精确+FVG对齐
- `detect_choch_v5(bars)` — V5 CHOCH: HH+Break / LL+Break
- `calc_bpr_v5(fvg_list, max_idx)` — V5 BPR: 基于FVG pair
- `detect_entries_v5(bars, params, enable_explore)` — V5 入口检测 — 多尺度FVG + 弹性评分 + 三通道
- `backtest_v5(bars, mode, params, enable_explore)` — V5 回测: 支持所有通道
- `simulate_entry_v5(entry, bars, sl_buffer)` — V5 模拟一笔entry — 带SL缓冲区
- `compute_v5_score(per_stock)` — V5评分: WR优先 + 信号量 + Sharpe
- `fetch_hubble(url, timeout)` — 
- `get_klines_v5(symbol, interval, limit)` — 
- `get_stock_list_v5()` — 

## hermes\scripts\smc_engine_v53.py
- `calc_atr(klines, period)` — 
- `get_vol_profile(bars)` — 
- `find_swing_highs(bars, lookback)` — 找到波段高点
- `find_swing_lows(bars, lookback)` — 找到波段低点
- `detect_fvg_v53(bars, params)` — FVG检测 — 简单的gap检测
- `detect_sweep_v53(bars, params)` — Sweep检测 — 精准影线
- `detect_ob_v53(bars, params)` — OB检测
- `detect_ms_structure(bars)` — 检测市场结构 (MS) — HH/HL/LH/LL
- `compute_structural_sl(bars, entry_idx, direction, default_sl_pct, ep)` — 计算结构止损 — 找最近的结构高低点
- `compute_structural_tp(bars, entry_idx, direction, sl_price, ep)` — 计算结构止盈 — 找到最近的FVG/OB作为盈利目标
- `detect_entries_v53(bars, params)` — V5.3入口检测 — 结构确认 + 信号源计数
- `backtest_v53(bars, params)` — V5.3回测
- `simulate_entry_v53(entry, bars)` — 模拟一笔 — 带结构止损确认
- `compute_v53_score(trades)` — 评分: WR * 0.5 + PF * 0.3 + N * 0.2
- `fetch(url, timeout)` — 
- `get_bars(symbol, interval, limit)` — 
- `load_bars(symbol, interval, limit)` — 加载K线, 优先缓存
- `get_stock_list()` — 

## hermes\scripts\smc_engine_v54.py
- `get_adaptive_params(atr_pct, preset)` — 根据波动率动态生成参数
- `calc_atr(klines, period)` — 
- `get_vol_profile(bars)` — 
- `detect_fvg(bars, min_width)` — FVG检测 — 三根K线gap
- `detect_sweep(bars, lookback, wick_ratio)` — Sweep检测 — 影线突破前高/前低
- `detect_ob(bars)` — OB检测 — 大实体后确认
- `detect_cho_choch(bars)` — CHoCH检测 — 趋势反转
- `compute_swing_sl_tp(bars, entry_idx, direction, ep, atr)` — 用波段结构计算止损止盈
- `detect_entries_v54(bars, params)` — V5.4主入口检测:
- `backtest_v54(bars, params)` — V5.4回测 — 结构止损
- `simulate_v54_trade(entry, bars)` — 模拟一笔交易 — 支持移动止损
- `compute_score(trades)` — 评分
- `fetch(url, timeout)` — 
- `load_bars(symbol, interval, limit)` — 

## hermes\scripts\smc_engine_v6.py
- `fetch_hubble(url, timeout)` — 
- `get_klines(symbol, interval, limit)` — 
- `load_cached_bars(symbol, limit)` — 
- `calc_atr(klines, period)` — 
- `calc_ema(values, period)` — 
- `calc_rsi(klines, period)` — 
- `calc_macd(klines, fast, slow, signal)` — 
- `calc_vol_ratio(bars, idx, lookback)` — 比较idx处成交量和过去lookback的平均成交量
- `classify_market_state(bars)` — 三维分类: 波动率 / 趋势强度 / 成交量活性
- `detect_fvg_v6(bars, threshold, window_sizes)` — V6多窗口FVG: 使用不同K线组合检测FVG
- `detect_swing_highs(klines, left, right)` — 
- `detect_swing_lows(klines, left, right)` — 
- `detect_sweep_v6(bars, lookback, wick_min, use_volume_confirm)` — V6 Sweep检测: 带成交量确认
- `detect_choch_v6(bars, lookback)` — V6 CHOCH: 多时间框架确认
- `detect_ob_v6(bars, fvg_list)` — V6 OB: 成交量确认 + FVG对齐
- `calc_bpr_v6(fvg_list, lookback)` — 
- `get_v6_params_from_state(vol_state, trend_state, vol_active)` — 基于市场状态返回参数集
- `score_signal_v6(direction, bars, idx, fvg, sweep_near, ob_near)` — V6评分系统 (加权多因子)
- `detect_entries_v6(bars, params, state_params)` — V6入口检测 — 四层信号质量
- `simulate_entry_v6(entry, bars)` — 
- `backtest_v6(bars, mode, params)` — 
- `evaluate_trades(trades, name)` — 
- `compute_score_v6(trades)` — 
- `grid_param_search(symbol, base_params, param_grid)` — 网格搜索: 在param_grid范围内搜索最佳参数

## hermes\scripts\smc_engine_v61.py
- `fetch_hubble(url, timeout)` — 
- `get_klines(symbol, interval, limit)` — 
- `load_cached_bars(symbol, limit)` — 
- `calc_atr(klines, period)` — 
- `calc_vol_ratio(bars, idx, lookback)` — 
- `calc_ema(values, period)` — 
- `calc_rsi(klines, period)` — 
- `detect_swing_highs(klines, left, right)` — 
- `detect_swing_lows(klines, left, right)` — 
- `classify_market_state(bars)` — 
- `detect_fvg_standard_v6(bars, threshold)` — 标准FVG 3K
- `detect_sweep_v6(bars, lookback, wick_min)` — 
- `detect_choch_v6(bars, lookback)` — 
- `detect_ob_v6(bars, fvg_list)` — 
- `calc_bpr_v6(fvg_list, lookback)` — 
- `get_params_from_state(vol, trend, active)` — 基于市场状态生成优化参数
- `score_fvg_signal(direction, bars, idx, fvg, sw, ob)` — 
- `detect_entries_v61(bars, params)` — V6.1 高效入口
- `simulate_entry(e, bars)` — 
- `backtest_v61(bars, mode, params)` — 
- `evaluate_v6(trades, name)` — 
- `compute_score_v61(trades)` — 
- `genetic_search(symbols, base_params, generations, pop_size, mutation_rate)` — 遗传算法参数搜索
- `random_params()` — 
- `crossover(p1, p2)` — 
- `mutate(p)` — 
- `clamp(p)` — 
- `fitness(params)` — 

## hermes\scripts\smc_engine_v62.py
- `calc_adx(bars, period)` — 计算ADX趋势强度
- `calc_ema(bars, period)` — 简单EMA
- `detect_entries_v62(bars, sp)` — V6.2 入口检测 — 加入趋势过滤 + 动态SL/TP
- `single_stock_scan_v62(code, sp)` — V6.2 单股票扫描 — 复用V6.1的数据加载
- `quick_scan_62(code, sp)` — 兼容接口
- `ema(data, period)` — 

## hermes\scripts\smc_engine_v7.py
- 类: AdaptiveEngine, Population
- `get_param_keys()` — 
- `random_param()` — 
- `mutate_param(p, rate, intensity)` — 参数变异
- `crossover_param(p1, p2)` — 两点交叉
- `check_proxy()` — 检查代理状态，返回(ok, status_dict)
- `restart_proxy()` — 重启代理
- `logger(msg)` — 
- `ensure_v62_imports()` — 确保V6.2可用
- `evaluate_params(params, stocks, max_stocks)` — 评估一组参数 → 返回评分和详细指标
- `bayesian_refinement(best_params, history, stocks, n)` — 简易贝叶斯优化 — 用高斯过程思想：根据历史结果，在最佳点附近精细搜索
- `load_stock_list()` — 加载候选股票列表
- `run_v7(iters, pop_size, stocks_n)` — 运行V7全自动优化
- `save_state(best_params, best_score, best_details, history, pop, gen)` — 
- `write_live_status(gen, total, best_score, best_details, strategy)` — 写实时状态供WebUI读取
- `quick_scan_v7(code, params)` — 对外接口：用最佳参数扫描单只股票
- `update(self, best_score, generation)` — 更新策略状态
- `get_mutation_rate(self)` — 
- `get_crossover_rate(self)` — 
- `initialize(self, seed_params)` — 
- `evaluate_all(self, stocks, n)` — 评估整个种群
- `get_best(self)` — 
- `get_diversity(self)` — 计算种群多样性
- `select(self, n)` — 锦标赛选择
- `evolve(self, adaptive_engine, stocks, n)` — 种群进化一代

## hermes\scripts\smc_engine_v7_plus.py
- 类: AdaptiveEngineV3
- `calc_rr_bonus(rr)` — RR激励函数 — 非线性
- `score_v7plus(is_d, oos_d, params, max_stocks)` — V7+评分函数 V2
- `check_proxy()` — 
- `random_param()` — 
- `clamp_params(p)` — 
- `mutate_params(p, scale, force_rr_high)` — 
- `crossover(p1, p2)` — 
- `get_suffix(code)` — 
- `get_kline(code, days)` — 
- `get_stock_list()` — 
- `detect_fvg(klines, fvg_th)` — 检测FVG (Fair Value Gap)
- `detect_ob(klines, score_th)` — 检测OB (Order Block)
- `evaluate_params(params, stocks, max_stocks)` — 评估一组参数在stocks上的表现
- `_evaluate_stocks(stocks, sp)` — 对一组股票运行策略评估
- `_write_live(gen, total, best_score, best_details, strategy)` — 
- `run_v7plus(total_iters, pop_size, stocks_n)` — 
- `update(self, best_score, best_rr, generation)` — 
- `get_mutation_scale(self)` — 

## hermes\scripts\smc_engine_v7_v3.py
- `sfx(c)` — 
- `getk(code, days)` — 
- `get_stocks()` — 
- `detect_all(klines)` — 从K线检测所有SMC结构
- `eval_code(code, sp, min_fvg_pct, fvg_lookback)` — 基于SMC结构评估:
- `calc_sc(is_wr, oos_wr, is_pf, oos_pf, is_t, oos_t)` — 
- `rand_p()` — 
- `mutate(p, scale)` — 
- `cross(a, b)` — 
- `run(iters, pop_size, is_n, oos_n)` — 
- `fe(p, stks)` — 

## hermes\scripts\smc_engine_v8.py
- `calc_atr(klines, period)` — 
- `get_vol_profile(bars)` — 
- `detect_fvg_v8(bars, params)` — V8 FVG检测 — 更精确的gap计算
- `detect_sweep_v8(bars, params)` — V8 Sweep检测
- `detect_ob_v8(bars, params)` — V8 OB检测 — 带强度过滤
- `detect_ms_v8(bars)` — V8市场结构检测 — 更精确的趋势判断
- `detect_bpr_v8(bars)` — V8 Breaker检测 — 价格突破关键结构
- `detect_entries_v8(bars, params)` — V8入口检测 — 多层信号融合
- `backtest_v8(bars, params)` — V8回测
- `simulate_entry_v8(entry, bars)` — 模拟一笔交易
- `compute_v8_score(trades)` — V8评分 — 三层引导:
- `fetch(url, timeout)` — 
- `get_bars(symbol, interval, limit)` — 
- `load_bars(symbol, interval, limit)` — 加载K线(优先缓存)
- `check_proxy_ok()` — 检查代理 — 返回True/False

## hermes\scripts\smc_engine_v82.py
- `calc_atr(klines, period)` — 
- `get_vol_profile(bars)` — 
- `detect_fvg_v82(bars, params)` — 
- `detect_sweep_v82(bars, params)` — 
- `detect_ob_v82(bars, params)` — 
- `detect_ms_v82(bars)` — 
- `detect_bpr_v82(bars)` — 
- `detect_entries_v82(bars, params)` — 
- `backtest_v82(bars, params)` — 
- `simulate_entry_v82(entry, bars)` — 
- `compute_v82_score(trades)` — V8.2评分 — 四层平衡引导:
- `fetch(url, timeout)` — 
- `get_bars(symbol, interval, limit)` — 
- `load_bars(symbol, interval, limit)` — 
- `check_proxy_v8()` — 

## hermes\scripts\smc_engine_v83.py
- `calc_atr(klines, period)` — 
- `get_vol_profile(bars)` — 
- `load_bars(symbol, interval, limit)` — 加载并标准化K线数据 — 复用V8.2的缓存
- `check_proxy_v8()` — 检查代理状态
- `detect_fvg_v83(bars, params, avg_range)` — V8.3 FVG检测 — 自适应阈值 + 更精确的强度计算
- `detect_sweep_v83(bars, params)` — V8.3 Sweep检测 — 增强灵敏度
- `detect_ob_v83(bars, params)` — V8.3 OB检测 — 增强版
- `detect_ms_v83(bars)` — V8.3 Market Structure — 更精确
- `detect_bpr_v83(bars)` — V8.3 Breaker/BPR — 精确度提升
- `detect_entries_v83(bars, params)` — V8.3 Enhanced entry detection with forced RR
- `backtest_v83(bars, params)` — 
- `simulate_entry_v83(entry, bars)` — V8.3 模拟 — 含partial fill和max bars constraint
- `compute_v83_score(trades)` — V8.3 评分 — 五层平衡引导:
- `make_entry_key(idx, dir)` — 

## hermes\scripts\smc_engine_v84.py
- `hubble_api(endpoint, params)` — 调用Hubble API
- `fetch_kline_cached(symbol, period, count)` — 获取K线(缓存) — 智能匹配已缓存数据
- `kline_to_ohlcv(kline_data)` — 转换Hubble K线为OHLCV列表
- `calc_atr(ohlcv, period)` — 计算ATR
- `detect_fvg(ohlcv, min_width, merge_dist)` — 检测FVG — 三根K线: 第一根高<第三根低
- `detect_ifvg(ohlcv, min_width)` — 检测IFVG: 三根K线中间有重叠缺口
- `detect_sweep(ohlcv, lookback, wick_ratio)` — 检测Sweep — 价格突破前高/低后迅速反转
- `detect_ob(ohlcv, strength_min)` — 检测OB — 最后一段阴线/阳线
- `detect_bpr(ohlcv, lookback)` — 检测BPR — 价格回到FVG区域后反转
- `detect_msb(ohlcv, lookback)` — 检测MSB — 突破前高/低并维持
- `detect_all_signals(ohlcv, params)` — 检测所有类型信号, 返回信号列表
- `score_signal(signal, ohlcv)` — 给单个信号打分 (0-5)
- `evaluate_trades(ohlcv, params)` — 基于信号生成交易并评估盈亏
- `v84_score(eval_results)` — V8.4 RR优先评分
- `evaluate_params(params, stocks, progress_cb)` — 评估单组参数
- `main()` — 单次评估命令行

## hermes\scripts\smc_live_monitor.py
- `load_tradable_stocks(limit)` — 加载V14可交易股票及其最优参数
- `check_stock(symbol, sl_pct, tp_pct)` — 检查单只股票是否有入场信号
- `check_all_stocks(stocks, limit_per_run)` — 批量检查可交易股票
- `save_signals(signals)` — 保存/追加信号到日志
- `format_alert(signal)` — 格式化为推送消息
- `main()` — 

## hermes\scripts\smc_live_monitor_v38.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_v38_sl_lite(ohlcv, entry_idx, entry_price, signal, direction, structure_tree)` — V38.4结构SL计算 (轻量版用于实盘监控)
- `calc_v38_tp_lite(ohlcv, entry_idx, entry_price, all_signals, direction)` — V38.4结构TP计算 (轻量版)
- `calc_v38_trailing_lite(ohlcv, entry_idx, entry_price, initial_sl, tp_price, n)` — V38.4 3-profile trailing (轻量版)
- `check_stock_v38(ohlcv, symbol)` — V38.4实时信号检测 - 单股票
- `main()` — 

## hermes\scripts\smc_monitor.py
- `main()` — 

## hermes\scripts\smc_monitor_state.py
- `now_iso()` — 
- `ymd()` — 
- `date_key(v)` — 
- `t1_exit_allowed(pos, exit_dt)` — 
- `t1_entry_allowed(pick_date, entry_dt)` — A-share production entry hard gate: a pick can only be filled after its pick date.
- `should_delay_entry_until_next_trading_day(pick_date, source, entry_dt)` — True when an automatic daily pick must stay pending until a later trading day.
- `market_entry_allowed(ts)` — 
- `load_json(path, default)` — 
- `save_json(path, data)` — 
- `classify_pick(p)` — 
- `pick_key(p)` — 
- `is_same_day_pick(p)` — 
- `sample_class_for_position(pos)` — Classify whether a monitor position is clean production or diagnostic-only.
- `_parse_ymd(v)` — 
- `_pick_date(p)` — 
- `_f(v, default)` — 
- `_zone_bounds(p)` — 
- `enrich_pick_fields(p)` — Normalize production-critical pick fields without changing engine output.
- `_business_age_days(start, end)` — 
- `production_entry_gate(p, exec_price, source)` — Production-only validation before a pick becomes an OPEN/NEXT_DAY_PENDING position.
- `automatic_buy_authorized(p)` — Require registry + row-level BUY authorization; active metadata is insufficient.
- `live_execution_price(symbol)` — 
- `to_position(p, source, operator_note)` — 
- `load_trade_ledger()` — 
- `append_trade_event(action, pos, live)` — 
- `load_positions()` — 
- `save_positions(rows)` — 
- `fill_pending_orders()` — 
- `ingest_daily_picks(picks, source)` — 
- `add_manual_pick(symbol, entry_price, sl_price, tp1_price, note)` — 
- `close_review(pos, live, reason)` — 
- `update_with_live_results(live_picks)` — 
- `summary()` — 

## hermes\scripts\smc_opt_v55.py
- `default_params()` — 
- `randomize(cur, temp)` — 
- `crossover(p1, p2)` — 
- `evaluate(fp, stocks, max_s)` — 评估一组参数
- `run_opt(n_rounds)` — 主优化循环

## hermes\scripts\smc_optimizer_v2.py
- 类: ParamGeneratorV2
- `evaluate_score_v6(per_stock_results)` — 从每只个股结果计算综合评分
- `quick_evaluate(params, stock_list, n_stocks, strategy)` — 快速评估一组参数, 在n_stocks上回测combo策略
- `multi_strategy_eval(params, stock_list, n_stocks)` — 同时评估三种策略
- `main()` — 
- `random(self)` — 
- `get_default(self)` — 
- `get_best(self)` — 
- `mutate_best(self, rate)` — 在当前best附近变异
- `crossover_best_two(self)` — 从top2做交叉
- `next(self)` — 
- `record(self, params, score, stats)` — 

## hermes\scripts\smc_optimizer_v3.py
- 类: V3Optimizer
- `load_stocks(self)` — 
- `random_params(self)` — 
- `default_params(self)` — 
- `mutate(self, base, rate)` — 
- `crossover(self)` — 
- `score_params(self, params, n_stocks)` — 评估一组参数
- `run(self, iterations, n_stocks)` — 

## hermes\scripts\smc_optimizer_v4.py
- 类: V4Optimizer
- `load_stocks(self)` — 加载并打乱股票列表
- `random_params(self)` — 随机参数
- `default_params(self)` — 默认参数
- `to_v4_params(self, opt_params)` — 将优化参数转换为V4引擎可用的参数字典
- `mutate(self, base, rate)` — 变异
- `crossover(self)` — 交叉遗传
- `local_search(self, base, spread)` — 局部精细搜索
- `score_params(self, params, n_stocks)` — 评估一组参数
- `run(self, iterations, n_stocks)` — 主运行循环
- `save_iteration(self, i, params, result, is_best)` — 保存单次迭代
- `save_final(self)` — 保存最终结果

## hermes\scripts\smc_optimizer_v4_5000.py
- 类: V4Optimizer5000
- `load_stocks(self)` — 加载所有股票
- `backtest_stock(self, code, name)` — 回测单只股票
- `evaluate_group(self, group_idx)` — 评估一组股票
- `run(self)` — 主循环
- `save_progress(self)` — 保存中间结果
- `save_final(self)` — 保存最终结果
- `print_summary(self, to_file)` — 打印汇总

## hermes\scripts\smc_optimizer_v4_5000_v2.py
- 类: V4MassScanner
- `get_klines_cached(symbol, interval, limit)` — 带缓存的K线获取
- `quick_detect(bars)` — 快速检测: 只用strict模式, 返回是否有信号+WR
- `process_single_stock(code_name)` — 处理单只股票
- `load(self)` — 
- `on_complete(self, future)` — 回调: 处理完成
- `run(self)` — 
- `final_report(self, total_time)` — 
- `save_results(self)` — 保存结果
- `save_webui_report(self)` — 保存WebUI可读报告

## hermes\scripts\smc_optimizer_v5.py
- 类: V5Optimizer
- `random_params()` — 
- `default_params()` — 
- `mutate(params, rate, spread)` — 
- `crossover(parents)` — 
- `big_mutate(params)` — 大幅变异 — 跳出局部最优
- `_save_state(self)` — 
- `_load_state(self)` — 
- `load_stocks(self)` — 
- `evaluate(self, params)` — 评估一组参数 — 在N只股票上回测
- `run(self)` — 
- `_print_result(self, gen, result)` — 

## hermes\scripts\smc_optimizer_v53.py
- `default_params()` — 
- `randomize_params(current, temperature)` — 随机生成参数, 如果提供了current则在其附近扰动
- `evaluate_params(params, stock_list, max_stocks)` — 评估一组参数在多个股票上的表现
- `run_optimization(n_rounds, n_start, resume)` — 运行优化

## hermes\scripts\smc_optimizer_v54.py
- `flat_to_engine(flat_params, atr_pct)` — 将平面参数转换为引擎接受的参数dict
- `default_flat_params()` — 
- `randomize_flat_params(current, temperature)` — 随机扰动参数
- `evaluate_params_flat(flat_params, stock_list, max_stocks)` — 评估一组参数在所有股票上的加权表现
- `run_optimization(n_rounds, n_start, resume)` — 运行全自动优化

## hermes\scripts\smc_optimizer_v55.py
- `default_params()` — 
- `params_to_engine(flat_params, atr_pct)` — V5.5引擎参数转换 (支持波动率自适应)
- `randomize(current, temperature)` — 参数随机化 (带保底)
- `crossover(p1, p2)` — 遗传交叉
- `load_bars(symbol)` — 直接从缓存加载K线
- `calc_atr_v2(bars, period)` — 
- `quick_vol_profile(bars)` — 
- `quick_backtest(bars, params)` — 极简回测 (内联, 无外部依赖)
- `score_trades(trades)` — 
- `evaluate(flat_params, stocks, max_s)` — 评估参数
- `run_optimization(n_rounds)` — 全自动多策略优化

## hermes\scripts\smc_optimizer_v5_v2.py
- 类: V5OptimizerV2
- `random_params_v2()` — 
- `default_params_v2()` — 
- `mutate_v2(params, rate)` — 
- `crossover_v2(parents)` — 
- `compute_v2_score(total_stats)` — total_stats: {
- `_save_state(self)` — 
- `_load_state(self)` — 
- `load_stocks(self)` — 
- `evaluate(self, params)` — 评估: 在固定stock pool上, 获取总信号统计
- `run(self)` — 
- `_check_best(self, result, params)` — 
- `_print_result(self, gen, result)` — 

## hermes\scripts\smc_optimizer_v8.py
- `check_proxy()` — 检查代理状态
- `restart_proxy()` — 重启代理
- `log(msg)` — 
- `save_live(round_num, best_score, best_wr, best_n, status, details)` — 写入实时状态
- `save_progress(history)` — 写入迭代历史
- `default_params()` — 
- `random_params()` — 完全随机参数
- `mutate_params(current, temperature)` — 在当前位置附近扰动参数
- `evaluate_params(params, stock_list)` — 评估一组参数在股票池上的表现
- `main()` — 

## hermes\scripts\smc_optimizer_v82.py
- `check_proxy()` — 
- `restart_proxy()` — 
- `log(msg)` — 
- `save_live(round_num, best_score, best_wr, best_n, status, details)` — 
- `save_progress(history)` — 
- `default_params()` — 
- `random_params()` — 生成随机参数（支持种子收缩）
- `mutate_params(current, temperature)` — 
- `crossover_params(p1, p2, temperature)` — 交叉+小扰动 — 结合两个parent的基因
- `evaluate_params(params, stock_list)` — 
- `main()` — 

## hermes\scripts\smc_optimizer_v83.py
- `check_proxy()` — 
- `restart_proxy()` — 
- `log(msg)` — 
- `save_live(round_num, best_score, best_wr, best_n, status, details)` — 
- `save_progress(history)` — 
- `default_params()` — 
- `random_params()` — Generate random params (with optional seed tightening)
- `mutate_params(current, temperature)` — Mutate with V8.3 RR constraint
- `crossover_params(p1, p2, temperature)` — Uniform crossover + small perturbation
- `blend_crossover(p1, p2, alpha)` — Blend crossover: genes from [min-α*d, max+α*d]
- `hill_climb(params, iterations, step_size)` — Local hill climbing around best params
- `init_islands()` — Initialize independent island populations
- `migrate(islands)` — Migrate best individuals between islands
- `evaluate_params(params, stock_list)` — 
- `main()` — 

## hermes\scripts\smc_optimizer_v84.py
- 类: V84Optimizer
- `parse_args()` — 
- `random_params(space, seed_params, tighten_pct)` — 生成随机参数
- `mutate_params(params, space, mutation_rate)` — 突变
- `crossover_params(p1, p2, space)` — 交叉
- `warmup_cache()` — 预热所有股票K线缓存
- `save_state(self)` — 保存状态
- `save_best(self)` — 保存最佳参数
- `save_history(self)` — 保存历史
- `save_elite(self)` — 保存精英池
- `evaluate(self, params)` — 评估一组参数
- `update_best(self, score, params, result)` — 更新最佳
- `add_to_elite(self, score, params, result)` — 加入精英池
- `run(self)` — 主优化循环

## hermes\scripts\smc_optimizer_v85.py
- `log(msg)` — 
- `safe_read_json(path)` — 
- `get_best_wr()` — 
- `save_best_as_seed(round_num)` — Save current best params as seed for next round
- `check_proxy()` — Wait for proxy to be ready
- `wait_for_round_complete(check_interval, max_wait)` — Poll live_status.json until round completes
- `run_optimizer_round(iters, stocks, tighten, seed)` — Run a single optimizer round
- `write_status(st, rnd, total, best_wr)` — Update live_status.json
- `main()` — 

## hermes\scripts\smc_proxy_guardian_v5.py
- `write_status()` — 
- `run(cmd, timeout)` — 
- `check_process()` — 
- `check_port()` — 
- `check_internet()` — 
- `check_nodes()` — 检查节点存活状态
- `full_check()` — 
- `restart_proxy()` — 
- `cleanup_zombies()` — 清理僵尸mihomo进程
- `main_loop()` — 主循环

## hermes\scripts\smc_trade_viewer.py
- 类: Handler
- `load_ohlcv(symbol)` — 
- `build_html(symbol)` — 
- `do_GET(self)` — 

## hermes\scripts\smc_trade_viewer_v2.py
- 类: Handler
- `format_date(d)` — Format date to YYYY-MM-DD string from various input formats.
- `load_ohlcv(symbol)` — 
- `load_60min_ohlcv(symbol)` — Load 60min kline data.
- `short_sig_label(t)` — Return short label for a signal type.
- `compute_sl_tp_from_signals(signals, entry_idx, entry_price, direction)` — Compute SL/TP based on SMC structure.
- `build_html(symbol)` — 
- `build_60min_signals(symbol)` — Detect signals on 60min data and map to daily xAxis dates.
- `do_GET(self)` — 

## hermes\scripts\smc_trade_viewer_v3.py
- 类: Handler
- `format_date(d)` — 
- `load_ohlcv(symbol)` — 
- `load_60min_ohlcv(symbol)` — 
- `short_sig_label(t)` — 
- `compute_sl_tp_from_signals(signals, entry_idx, entry_price, direction)` — 
- `compute_global_stats()` — Compute aggregate statistics from stock_results for stats panel.
- `build_html(symbol)` — 
- `build_60min_signals(symbol)` — 
- `build_global_stats_json()` — 
- `do_GET(self)` — 

## hermes\scripts\smc_tuner_v3.py
- `build_custom_entries(bars, params)` — V3.2入口检测 + 自定义参数
- `simulate_custom(entries, bars)` — 
- `detect_fvg_multi(bars)` — 
- `score_params(params, stocks, n_stocks)` — 
- `run()` — 

## hermes\scripts\smc_unified.py
- 类: Handler
- `load_v50_signal_snapshot(symbol)` — Load one symbol from the large V50 signal snapshot without parsing the full 700MB file.
- `_production_registry()` — 
- `_current_committed_data_epoch(fallback)` — For an EMPTY_BOOK, expose cache freshness without implying a buy license.
- `_production_empty_book()` — 
- `_v526_live_production()` — 
- `_v526_state()` — 
- `_promoted_contract_dir()` — 
- `_load_v103a_stability_report()` — 
- `_pct_cell(v)` — 
- `_build_v103a_stability_html()` — 
- `_frontend_version_label()` — Visible production label: keep V88 data-routing shell, show promoted contract.
- `load_json(path, default)` — 
- `_load_json_dict(path, default)` — 
- `_load_json_list(path, default, limit)` — 
- `load_v45_bundle(version, limit_events, limit_rows)` — 
- `is_winner(t)` — True if trade is winning. Modern engines use pnl_pct; legacy may only use 'won'.
- `exit_key(t_or_reason)` — Canonical exit reason key for V25-V31 frontend/diagnostics sync.
- `exit_label(reason)` — 
- `_date_key(v)` — 
- `_float_or_zero(v)` — 
- `_apply_smc_field_contract(row, default_engine)` — Fill the cross-surface SMC field contract without changing row semantics.
- `_contract_summary_html(rows, title, limit)` — Render a compact cross-surface contract block for frontend parity checks.
- `_parse_date_key(v)` — 
- `_trade_cutoff_from_data(trades)` — 
- `normalize_v27_trades(trades)` — Canonical contract for all frontend surfaces. Supports V27 and V28.
- `normalize_v27_picks(picks, trades)` — Keep picks synchronized with the active 3-year trade universe.
- `get_v44_summary_fast()` — Read lightweight summary from V44 full file without materializing all trades.
- `_active_pick_mtime()` — 
- `_merge_v66_daily_picks(raw_picks)` — 
- `_v88_latest_market_date()` — 
- `_latest_v88_scanner_rows(rows)` — V88 monitor shows the latest full-market scanner output, never old backtest rows.
- `_dedupe_v88_scanner_rows(rows)` — 
- `_last_cached_daily_price(symbol)` — 
- `_apply_current_price_live_guard(rows)` — 
- `_merge_v90_daily_picks(raw_picks)` — 
- `_merge_v91_shadow_picks(raw_picks)` — 
- `_v100_production_rows(rows)` — Frontend production contract: promoted audit files may contain all tiers;
- `_promoted_trade_file()` — 
- `_cache_valid()` — 
- `_refresh_cache()` — 
- `get_trades_cached(lite)` — 
- `_get_version_trades_uncached(version, lite)` — Return trades for a requested frontend version without changing ACTIVE_VERSION.
- `get_version_trades(version, lite)` — Cached wrapper — v101_trades.json is huge; was 5.9s per kline request (FIX 2026-08-20).
- `get_version_picks(version)` — 
- `get_picks_cached()` — 
- `_invalidate_cache()` — Force all frontend data readers to reload active trade/pick/summary files.
- `_active_version_paths(version)` — Return canonical engine/output paths for the active frontend version.
- `get_v27_recent()` — 
- `_vdata(path, default)` — 
- `reload_trades()` — Fast — uses memory cache
- `reload_picks()` — Fast — uses memory cache
- `_max_trade_date(trades, field)` — 
- `_normalize_pick_scope(p, latest_trade_date)` — Normalize pick contract. V44 legacy ACTIVE means historical-best, not current active.
- `get_all_picks_scoped(version)` — 
- `get_active_picks(include_reject, version)` — 
- `get_reject_picks(version)` — 
- `get_pick_contract_summary(version)` — 
- `reload_metrics()` — 
- `_active_report_stats(scope)` — Return report-level net stats for current promoted engine when available.
- `get_default_trades()` — 
- `_load_v20c_trades_for(symbol, klines, chart_date_idx)` — Load v20c backtest trades for symbol, enriched with prices/sub-signals (all versions).
- `_v20c_subsignals(src, entry_i, klines, date_idx, fallback_ed)` — Generate sub-signal chain for a v20c backtest trade at entry bar (for K-line tooltip/table
- `build_kline(symbol, version)` — 
- `build_dashboard(qs)` — 
- `build_equity_curve_data(trades, max_positions)` — Portfolio-aware equity curves. Dates are unique/sorted; trade cumulative is diagnostic onl
- `_filter_trades_by_window(trades, start, end, date_field)` — Return trades inside [start,end] by entry_date and sorted chronologically.
- `_v517_rr(t)` — 
- `_v517_audit_rows(rows, limit)` — 
- `_v517_period_metric_table(rows, period_field)` — 
- `build_v517_research_backtest()` — 
- `build_backtest(start, end)` — 
- `build_monitor(start, end)` — 
- `_historical_artifact_rows()` — Quarantined legacy rows for audit only; never current picks, positions, or production metr
- `_legacy_audit_rows(rows)` — 
- `build_historical_artifacts()` — 
- `_freshness_card()` — FIX(2026-08-19/22): 数据新鲜度标注卡片（选股时未更新量 + 实时刷新进度 → 前端展示，复用）
- `build_combo()` — 研究组合策略（SMC 三周期TP2-R20 + 内部人事件）展示页 — 只读研究，不写生产。
- `build_nav()` — 
- `_empty_book_page(title, detail)` — Production-only pages must not render quarantined historical artifacts.
- `_load_ops_latest()` — 
- `_v526_log_snapshot()` — Current V526 controller state; never render stale legacy ops as production.
- `_latest_data_date(ops)` — 
- `_fmt_date_label(v)` — 
- `_ops_scan_meta(ops)` — 
- `build_logs()` — 
- `build_stoploss()` — 
- `build_v45_page(version)` — 
- `build_analysis(start, end)` — 
- `build_compare()` — 
- `_load_v49_closed_loop_review()` — 
- `_autopsy_issue_rows(rows, limit)` — 
- `build_autopsy(start, end)` — 
- `build_resonance()` — Multi-Timeframe Resonance Dashboard
- `_api_resonance(self)` — API: MTF resonance data for all current picks.
- `build_diagnostics()` — V30 SMC Diagnostics page — cohort decomposition, root cause attribution.
- `build_effort_result()` — V517 read-only surface: audit artifacts + scanner-time state, never production picks.
- `build_docs()` — 
- `build_v144_preview()` — Read-only V144 lifecycle preview page; consumes dry-run API only.
- `build_live()` — 实时监控页面 — AJAX局部刷新,不重载整页
- `build_trade()` — 实时交易模拟页面
- `_scheduler_load_state()` — 
- `_scheduler_save_state(state)` — 
- `_scheduler_log(msg)` — 
- `_scheduler_due(now, hhmm)` — 
- `_scheduler_run_job(name, cfg, run_date, force, trigger)` — 
- `_internal_scheduler_enabled()` — Only an explicit truthy value may enable the in-process scheduler.
- `_scheduler_loop()` — 
- `start_internal_scheduler()` — 
- `g(item, key, default)` — 
- `_d(i)` — 
- `_shift(days)` — 
- `_monitor_position_engine(pos)` — 
- `build_rows(plist, limit)` — 
- `monitor_pos_row(p)` — 
- `dict_rows(d)` — 
- `file_rows(d)` — 
- `task_rows()` — 
- `rows(items, cols)` — 
- `dict_rows(d, limit)` — 
- `list_rows(items, cols)` — 
- `_badge(t, v)` — 
- `_fix_list(fixes)` — 
- `_exit_table(items)` — 
- `_market_table(items)` — 
- `_simple_table(items, fields)` — 
- `_quality_tables(grade_data)` — 
- `_rank_table(items, title, limit)` — 
- `fetch_live_prices(cls, codes)` — Batch fetch real-time prices from Tencent (Hubble fallback if down). codes: list of pure n
- `do_HEAD(self)` — 
- `do_GET(self)` — 
- `do_POST(self)` — 
- `_post_qs(self)` — 
- `_route(self)` — 
- `_html(self, content)` — 
- `_json(self, data)` — 
- `_api_live_combo(self)` — FIX(2026-08-26): COMBO 模拟持仓实时价 + TP/SL 状态（/live AJAX 每 5 秒调用）
- `_api_live_prices(self)` — 返回实时价格+SL/TP状态
- `_api_trade_status(self)` — 
- `_api_trade_scan(self, qs)` — 
- `_api_trade_check(self)` — 
- `_static_file(self, path, mime)` — 
- `_api_kline_full(self, qs)` — 
- `_api_reselect(self, qs)` — 触发手动重新选股/自定义回测 — 支持 start/end/update_kline 参数。
- `_api_history(self)` — 列出所有历史选股记录
- `_api_history_load(self, qs)` — 加载指定日期的历史选股
- `_api_diagnostics(self)` — Return active-version diagnostics JSON.
- `_api_summary(self)` — 
- `grab(name)` — 
- `_batch_int(name, default)` — 
- `_batch_href(page)` — 
- `reached_at_least(stage)` — 
- `symbol_list(rows)` — 
- `_subs_tt(t)` — 
- `_subs_tt_combo(t)` — 
- `cell(value)` — 
- `cell(value)` — 
- `_position_engine(pos)` — 
- `pick_recent_date(p)` — 
- `_last_cached_bar(symbol)` — 
- `fmt_date(v)` — 
- `_sum(rs)` — 
- `_nearest_wave_ref(ev)` — 
- `_chart_idx_for_date(v)` — 
- `_snap_idx_from_date(v)` — 

## hermes\scripts\smc_unified_v19.py
- 类: Handler
- `get_v19_backtest_files()` — 
- `load_v19_backtest(symbol_code)` — 
- `build_v19(symbol_code)` — 
- `do_GET(self)` — 
- `log_message(self, format)` — 

## hermes\scripts\smc_v4_report.py

## hermes\scripts\smc_v55.py
- `calc_atr(klines, period)` — 
- `get_vol(bars)` — 
- `get_layer_params(fp, atr_pct)` — 获取波动率层的参数
- `backtest_all(bars, flat_params)` — V5.5完整回测 — 返回trade list
- `score_trades(trades)` — V5.5评分: WR+PF+Return 均衡
- `fetch(url, timeout)` — 
- `load_bars(symbol, forced_refresh)` — 

## hermes\scripts\smc_v7v3_status.py

## hermes\scripts\smc_watchdog.py
- `log(msg)` — 
- `check_process(cmd)` — 
- `check_port(port)` — 
- `start_service(name, config)` — 启动一个服务
- `stop_service(name, config)` — 停止一个服务
- `start_optimizer(iterations, stocks)` — 启动V4优化器
- `stop_optimizer()` — 停止优化器
- `get_status()` — 获取所有服务状态
- `print_status()` — 打印状态
- `main_loop()` — 主看门狗循环
- `cleanup()` — 

## hermes\scripts\smc_web_server_v2.py
- 类: SMCWebHandler
- `start_status_api()` — 
- `main()` — 
- `do_OPTIONS(self)` — 
- `do_GET(self)` — 
- `proxy_request(self, url)` — 代理请求到API服务器
- `end_headers(self)` — 
- `log_message(self, format)` — 

## hermes\scripts\smc_web_server_v3.py
- 类: Handler
- `do_OPTIONS(self)` — 
- `do_GET(self)` — 
- `end_headers(self)` — 

## hermes\scripts\smc_web_server_v4.py
- 类: Handler
- `do_OPTIONS(self)` — 
- `_cors_headers(self)` — 
- `_proxy_request(self, target_url)` — 代理请求到后端API并返回结果
- `do_GET(self)` — 
- `end_headers(self)` — 

## hermes\scripts\smc_web_status_api.py
- 类: StatusHandler
- `load_json(path, default)` — 
- `get_latest_iter_file(dir_path)` — 获取最新的迭代文件
- `get_all_iter_files(dir_path)` — 
- `collect_status()` — 收集所有系统状态
- `main()` — 
- `do_OPTIONS(self)` — 
- `do_GET(self)` — 
- `json_response(self, data, code)` — 
- `log_message(self, format)` — 

## hermes\scripts\smc_web_status_api_v54.py
- 类: Handler
- `load_json(path, default)` — 
- `do_OPTIONS(self)` — 
- `do_GET(self)` — 
- `get_status(self)` — 合并V8/V7/代理状态
- `get_progress(self)` — V8迭代历史
- `get_best(self)` — V8最佳参数
- `get_proxy(self)` — 代理状态
- `get_history_chart(self)` — V8评分+WR趋势
- `get_health(self)` — 综合健康检查
- `get_kline(self, symbol)` — 获取特定股票的K线+信号
- `log_message(self, format)` — 静默请求日志

## hermes\scripts\smc_web_status_api_v82.py
- 类: Handler
- `load_json(path, default)` — 
- `do_OPTIONS(self)` — 
- `do_GET(self)` — 
- `get_status(self)` — 合并V8.2/V8/V7/代理状态
- `get_progress(self)` — V8.2迭代历史
- `get_best(self)` — V8.2最佳参数
- `get_proxy(self)` — 代理状态
- `get_history_chart(self)` — V8.2评分+WR趋势
- `get_health(self)` — 综合健康检查
- `get_kline(self, symbol)` — 获取特定股票的K线+信号(使用V8.2引擎)
- `log_message(self, format)` — 

## hermes\scripts\smc_web_status_api_v83.py
- 类: StatusHandler
- `safe_read_json(path)` — 
- `query_mihomo_api(endpoint)` — 从mihomo API实时获取数据
- `get_proxy_status()` — 获取代理状态: 先从mihomo API实时查询，失败则回退到文件
- `build_v83_status()` — 构建仅V8.3状态
- `build_status_response()` — 构建统一状态响应
- `main()` — 
- `log_request(self, code, size)` — 
- `do_GET(self)` — 
- `do_OPTIONS(self)` — 

## hermes\scripts\smc_webui_api.py

## hermes\scripts\smc_webui_v54.py
- 类: V54WebHandler
- `main()` — 
- `do_OPTIONS(self)` — 
- `do_GET(self)` — 
- `end_headers(self)` — 
- `log_message(self, format)` — 

## hermes\scripts\stats_details.py

## hermes\scripts\stats_details2.py

## hermes\scripts\status_report.py

## hermes\scripts\temp_x_debug.py

## hermes\scripts\temp_x_fix.py

## hermes\scripts\temp_x_test2.py

## hermes\scripts\temp_x_test3.py

## hermes\scripts\test_akshare_60min.py

## hermes\scripts\test_api.py

## hermes\scripts\test_api2.py

## hermes\scripts\test_internal_scheduler_contract.py
- `load_module(tmpdir)` — 
- `test_scheduler_runs_once_per_day_and_manual_force_reruns()` — 

## hermes\scripts\test_monitor_entry_execution_contract.py
- `load_module(tmpdir)` — 
- `pick()` — 
- `test_stale_historical_pick_never_opens_at_contract_price()` — 
- `test_trading_time_fill_uses_live_price_even_for_contract_scanner_pick()` — 
- `test_active_flag_without_buy_valid_never_creates_position()` — 
- `test_non_trading_time_auto_pick_waits_next_day_not_open_contract_price()` — 
- `test_same_day_auto_pick_waits_next_day_even_during_trading_time()` — 
- `test_next_day_pending_fill_uses_live_price_and_sets_buy_date()` — 

## hermes\scripts\test_playwright_login.py

## hermes\scripts\test_playwright_x.py

## hermes\scripts\test_proxy.py

## hermes\scripts\test_proxy_60min.py

## hermes\scripts\test_retry_mechanisms.py
- `test(name, ok, detail)` — 

## hermes\scripts\test_seq_v14.py

## hermes\scripts\test_signals_fix.py

## hermes\scripts\test_twikit.py
- `parse_cookies(cookie_str)` — 

## hermes\scripts\test_twikit2.py
- `parse_cookies(cookie_str)` — 

## hermes\scripts\test_twikit_login.py

## hermes\scripts\test_twikit_patched.py

## hermes\scripts\test_v11_baseline.py

## hermes\scripts\test_v11_fast_bt.py
- `fast_backtest(ohlcv, symbol, params, tf, min_rr)` — 快速回测: 一次信号检测 → 序列匹配 → 按信号位置入场
- `compute_stats(trades)` — 
- `main()` — 

## hermes\scripts\test_v11_rolling.py
- 类: Trade
- `rolling_backtest_one_stock(ohlcv, symbol, params, min_confidence)` — Walk forward bar-by-bar, enter on resonance signal, exit on SL/TP hit
- `compute_stats(trades)` — 
- `main()` — 

## hermes\scripts\test_v11_smoke.py

## hermes\scripts\test_v11_smoke2.py

## hermes\scripts\test_v4.py

## hermes\scripts\test_v55_result.py

## hermes\scripts\test_verify_fix.py

## hermes\scripts\test_x_direct_api.py
- `parse_cookies(s)` — 

## hermes\scripts\test_xapi_direct.py

## hermes\scripts\tests\test_v81_contextual_smc_generator.py
- `bar(t, o, h, l, c)` — 
- `test_accumulation_environment_allows_up_continuation_bos_poi_reclaim()` — 
- `test_mixed_environment_blocks_continuation_even_when_bos_and_poi_exist()` — 
- `test_bear_risk_allows_only_ssl_sweep_choch_reversal_not_plain_bos()` — 
- `test_liquidity_target_must_be_above_entry_not_old_break_level()` — 
- `test_poi_requires_discount_location_and_unbroken_reclaim_before_entry()` — 
- `test_exit_semantics_distinguish_target_poi_break_and_trend_damage()` — 

## hermes\scripts\trend_v4.py

## hermes\scripts\try_keyring.py

## hermes\scripts\v10\__init__.py

## hermes\scripts\v10\per_stock_opt.py
- `optimize_per_stock(symbol, backtest_fn, global_best, iterations, verbose)` — Optimize parameters for a single stock via hill climbing.
- `_mutate(params, rate)` — Mutate per-stock optimizable parameters within allowed ranges.
- `_param_abs_bounds(param)` — Absolute bounds for each parameter.
- `_score(result)` — Score a backtest result. Higher = better.
- `_empty_stock_result(symbol, params)` — 
- `batch_optimize(stocks, backtest_fn, global_best, iterations_per_stock, verbose)` — Run per-stock optimization for a list of stocks.
- `save_per_stock_params(results, global_best)` — Save per-stock optimized parameters to JSON.
- `load_per_stock_params()` — Load per-stock optimized parameters.
- `get_params_for_stock(symbol, global_best)` — Get parameters for a specific stock.
- `compute_per_stock_stats(results)` — Compute statistics across all per-stock optimizations.

## hermes\scripts\v10\resonance_engine.py
- 类: ResonanceScore
- `calc_tf_resonance(tf_directions, tf_strengths)` — Calculate timeframe resonance: do higher TFs agree with target?
- `calc_indicator_resonance(signals, lookback_idx)` — Calculate indicator confluence within a local window.
- `calc_swing_resonance(swing_tree)` — Calculate swing point resonance from hierarchy tree.
- `calc_sequence_resonance(seq_result)` — Calculate sequence resonance from signal sequencer output.
- `evaluate_full_resonance(tf_directions, signals, swing_tree, seq_result, symbol, lookback_idx)` — Evaluate all four resonance dimensions and produce final score.
- `get_resonance_grade(score)` — Get human-readable grade and action from resonance score.
- `adjust_params_for_phase(base_params, market_phase)` — Adjust trading parameters based on market phase.
- `build_resonance_report(symbol, resonance, phase, seq_result, swing_result)` — Generate a human-readable resonance report.
- `total(self)` — Weighted total resonance score.
- `layers(self)` — Count how many resonance layers are active (>0.5).
- `expected_wr(self)` — Estimated win rate based on resonance layers.
- `to_dict(self)` — 
- `bar(label, value, max_val)` — 

## hermes\scripts\v10\run_per_stock_opt.py
- `v10_backtest_fn(symbol, params)` — Backtest function for per-stock optimizer.
- `main()` — 

## hermes\scripts\v10\signal_sequencer.py
- `_normalize_signal(signal)` — Convert a raw signal dict to a sequence token for pattern matching.
- `analyze_signal_sequence(raw_signals)` — Analyze signal sequence and identify high-quality patterns.
- `_match_subsequence(token_list, pattern, min_steps)` — Check if pattern appears as a subsequence in token_list.
- `_same_family(token, pattern_step)` — Check if token belongs to the same signal family as pattern_step.
- `score_entry_from_sequence(seq_result, base_score)` — Calculate entry quality score based on sequence analysis.
- `multi_tf_sequence_analyze(tf_signals)` — Analyze signal sequences across multiple timeframes.
- `quick_sequence_check(raw_signals)` — One-call sequence analysis and entry scoring.

## hermes\scripts\v10\smc_backtest_v10.py
- `evaluate_trades_v10(ohlcv, params, phase, swing_data, resonance_threshold)` — V10 trade evaluation with full resonance + sequence analysis.
- `_format_v10_trade_log(trade)` — Format V10 trade log with resonance info.
- `_empty_v10(reason)` — 
- `compute_score_v10(eval_results)` — Compute aggregate score from per-stock eval results.
- `batch_evaluate_v10(stocks, per_stock_params, global_params, resonance_threshold, progress_cb)` — Evaluate multiple stocks with per-stock parameters.
- `compare_v9_v10(symbol, params)` — Side-by-side comparison of V9 and V10 backtest results.
- `_wr(result)` — 
- `detect_all_signals(ohlcv, params)` — 
- `score_signal(signal, ohlcv)` — 
- `fetch_kline(symbol, interval, count)` — 
- `kline_to_ohlcv(kline)` — 
- `calc_atr_pct(ohlcv)` — 

## hermes\scripts\v10\smc_webui_v10.py
- `main()` — 

## hermes\scripts\v10\swing_points.py
- 类: SwingPoint, MarketStructure
- `find_swing_points(ohlcv, scales, min_strength)` — Multi-scale swing point detection.
- `_detect_pivots_at_scale(ohlcv, left, right, level, min_strength)` — Detect swing highs and lows at one scale.
- `_calc_pivot_strength(ohlcv, idx, left, right, is_high)` — Calculate pivot strength (0-1).
- `_cross_validate_pivots(all_pivots)` — Cross-validate: higher-level pivots confirm lower-level ones.
- `_build_structures(all_pivots)` — Build market structures from swing points.
- `_merge_pivots(primary, secondary)` — Merge two pivot lists, preferring primary when close.
- `_detect_market_phase(all_pivots, ohlcv)` — Detect current market phase from swing point patterns.
- `_calc_atr(ohlcv, period)` — Calculate Average True Range.
- `_build_hierarchy_tree(all_pivots, structures)` — Build hierarchical confirmation tree.
- `detect_swing_based_signals(ohlcv, swing_result)` — Generate enhanced signals using swing points.
- `swing_to_echarts(swing_result)` — Convert swing points to ECharts markPoint/markLine format.
- `analyze_swings(ohlcv)` — Quick swing analysis — returns the most important signals.
- `__repr__(self)` — 
- `bars(self)` — 
- `price_change(self)` — 
- `majority_direction(pivots)` — 

## hermes\scripts\v10\verify_v10.py
- `verify_one(symbol, params)` — Run V10 full analysis on one stock.
- `main()` — 

## hermes\scripts\v10_5\sequence_validator.py
- `normalize_signals_to_atoms(signals)` — Convert raw signals to atom tokens for sequence matching.
- `match_sequence(atoms, seq_def, max_gap)` — Check if a predefined sequence appears in the atom list.
- `backtest_sequence(ohlcv, atoms, seq_def, sl_pct, tp_pct, max_hold)` — Backtest a specific sequence pattern.
- `validate_all_sequences(ohlcv, atoms, sl_pct, tp_pct)` — Test ALL predefined sequences and rank by performance.
- `aggregate_cross_stock(stock_results)` — Aggregate sequence validation results across multiple stocks.
- `format_sequence_report(agg_result)` — Format cross-stock sequence validation as readable report.
- `validate_one_stock(symbol, ohlcv, signals, sl_pct, tp_pct)` — Run full sequence validation on one stock.

## hermes\scripts\v10_5\signals.py
- `detect_fvg_enhanced(ohlcv, min_width, merge_dist, strength_grades, detect_stack)` — Enhanced FVG detection with grading and stacking.
- `_classify_fvg_width(gap_pct, ohlcv, idx)` — Classify FVG width into 4 grades based on ATR.
- `_check_trend_alignment(ohlcv, idx, direction)` — Check if FVG aligns with the local trend.
- `_merge_fvgs(fvgs, max_gap)` — Merge FVGs that are close to each other.
- `_detect_fvg_stacks(fvgs, ohlcv)` — Detect FVG stacks: consecutive overlapping FVGs → strong zone.
- `_trace_mitigation(fvgs, ohlcv)` — Check if each FVG has been mitigated (price retraced into the gap).
- `detect_sweep_enhanced(ohlcv, lookback, wick_ratio, require_volume, require_reversal)` — Enhanced sweep detection with volume and reversal confirmation.
- `_classify_wick_ratio(ratio)` — Classify wick ratio into grades.
- `detect_ob_enhanced(ohlcv, strength_min, require_volume)` — Enhanced Order Block detection with volume and position analysis.
- `detect_choch_enhanced(ohlcv, lookback, min_confirm_bars)` — Enhanced CHOCH detection with swing-point awareness.
- `detect_liquidity_void(ohlcv, min_gap, min_vol_drop)` — Detect liquidity voids: large price gaps with low volume.
- `detect_rejection_block(ohlcv, min_wick_pct, min_reversal)` — Detect rejection blocks: price touches a level and strongly reverses.
- `detect_all_signals_enhanced(ohlcv, params)` — Run all enhanced signal detectors.
- `score_signal_enhanced(signal, ohlcv, swing_tree)` — Enhanced signal scoring (0-10 scale).

## hermes\scripts\v11\__init__.py

## hermes\scripts\v11\_analyze_sl_rr.py

## hermes\scripts\v11\_analyze_v467_rr.py

## hermes\scripts\v11\_analyze_v474_structure.py

## hermes\scripts\v11\_check_data.py

## hermes\scripts\v11\_check_dup_by_stock.py

## hermes\scripts\v11\_check_format.py

## hermes\scripts\v11\_check_per_stock_dupes.py

## hermes\scripts\v11\_check_t1.py

## hermes\scripts\v11\_check_t1_precise.py

## hermes\scripts\v11\_check_v474_dupes.py

## hermes\scripts\v11\_check_v474_out.py

## hermes\scripts\v11\_check_v476_trades.py

## hermes\scripts\v11\_compare_signals.py

## hermes\scripts\v11\_compare_v476_v477.py

## hermes\scripts\v11\_debug_mtf.py

## hermes\scripts\v11\_debug_mtf2.py

## hermes\scripts\v11\_debug_mtf3.py

## hermes\scripts\v11\_debug_ob_scan.py

## hermes\scripts\v11\_debug_v11_ob.py

## hermes\scripts\v11\_debug_v12_swings.py

## hermes\scripts\v11\_patch_t1.py

## hermes\scripts\v11\_review_detailed.py
- `load_ohlcv(sym)` — 

## hermes\scripts\v11\_review_v11v13_signals.py
- `load_ohlcv(sym)` — 
- `get_attr(sigs, attr, default)` — 

## hermes\scripts\v11\_run_variant.py
- `calc_v45_sl_forced_adaptive(ohlcv, entry_idx, entry_price, signal, entry_type, direction)` — 跳过信号边界SL和摆动点SL, 直接使用adaptive SL

## hermes\scripts\v11\_signal_count_compare.py

## hermes\scripts\v11\_test_signal_type.py

## hermes\scripts\v11\_test_type_chain.py

## hermes\scripts\v11\_test_v467_improvements.py
- `calc_v45_sl_forced_adaptive(ohlcv, entry_idx, entry_price, signal, entry_type, direction)` — 跳过信号边界SL和摆动点SL, 直接使用adaptive SL

## hermes\scripts\v11\_v11_baseline.py

## hermes\scripts\v11\_v12_debug_comprehensive.py
- `load_ohlcv(symbol)` — Load OHLCV data from cached JSON files.
- `compare_engines(symbols, max_stocks)` — Compare V11 vs V12 signal detection on multiple stocks.
- `deep_dive_stock(symbol)` — Deep dive into one stock to trace OB detection differences.

## hermes\scripts\v11\_v12_trace_ob.py
- `load_ohlcv(symbol)` — 
- `trace_ob_scan(symbol)` — For each swing high/low, trace why OB scan fails/succeeds.

## hermes\scripts\v11\_v13_coverage_check.py
- `cache_file(sym)` — 

## hermes\scripts\v11\_v13_debug_check.py

## hermes\scripts\v11\_v13_tune.py
- `patch(body, dis, near_w, vol)` — 

## hermes\scripts\v11\_v13_tune_params.py
- `make_param_fallback(body_min, dis_min, near_w, vol_min)` — Create a parameterized V13 OB detection with custom fallback params.
- `make_full_detector(ob_fn)` — Wrap OB function into full signal detection.
- `_run(ohlcv, adaptive, swings, tf)` — 
- `detect_all(ohlcv, params, tf)` — 

## hermes\scripts\v11\_v13_tune_runner.py

## hermes\scripts\v11\_v477_atr_analysis.py
- `calc_atr(ohlcv, period)` — 计算简单ATR

## hermes\scripts\v11\_v477_deep_analysis.py

## hermes\scripts\v11\_v477_report.py

## hermes\scripts\v11\_v477_trace_ob_sl.py
- `load_stock_kline(symbol)` — 
- `compute_atr(ohlcv, idx)` — 

## hermes\scripts\v11\adaptive_params.py
- `calc_stock_params(ohlcv, symbol, phase, tf, seed_params)` — 计算股票的完整自适应参数集
- `_calc_stock_stats(ohlcv)` — 计算股票统计特征
- `detect_market_phase(ohlcv)` — 检测当前市场阶段
- `save_per_stock_params(params)` — 保存每股票参数到文件
- `load_per_stock_params()` — 加载每股票参数
- `calc_sl_price(entry_price, direction, sl_pct, ohlcv)` — 计算止损价格
- `calc_tp_price(entry_price, sl_price, direction, tp_pct, rr_target)` — 计算止盈价格

## hermes\scripts\v11\adaptive_smc_v80.py
- `detect_sequences(signals)` — 
- `backtest_one(ohlcv, seqs)` — 
- `daily_to_weekly(d)` — 
- `weekly_trend(w)` — 
- `detect_operator_state(signals)` — Classify current operator based on signal density and quality
- `analyze_failure(trades)` — Why do trades fail?

## hermes\scripts\v11\adaptive_smc_v90.py
- `daily_to_weekly(d)` — 
- `weekly_trend(w)` — 
- `detect_state_v2(signals, ohlcv)` — Enhanced operator detection: density + volume + position + decay
- `get_60min_direction(sym, daily_bar_idx)` — Check 60min direction around daily bar. 
- `detect_sequences(signals)` — 
- `backtest_v8_simple(ohlcv, seqs)` — V8.0 style: zone_low * 0.995 SL, no state adjustment
- `backtest_v9(ohlcv, seqs, state, atr_pct, require_60min, sym)` — 

## hermes\scripts\v11\ai_analysis_engine.py
- `analyze_signal_quality(all_trades)` — 分析各信号类型的质量
- `analyze_entry_timing(trades_sample)` — 分析入场时机问题
- `analyze_exit_timing(trades_sample)` — 分析出场时机问题
- `analyze_ob_signal_detail(all_trades)` — 深度分析OB_Bull信号 — 逐维度检查
- `analyze_smart_money_context(all_trades, n_sample)` — SMC聪明钱上下文分析 — 检查信号前后是否有正确的SMC结构
- `generate_recommendations(quality, smc_context, entry_analysis, exit_analysis)` — 基于分析结果生成自适应推荐
- `run_full_analysis()` — 主分析流程

## hermes\scripts\v11\all_patterns_backtest.py
- `detect_sequences(signals, patterns, max_window)` — 检测所有匹配的时间序列模式.

## hermes\scripts\v11\all_signals_scan.py
- `detect_sequences(signals)` — 

## hermes\scripts\v11\analyze_v500.py

## hermes\scripts\v11\backtest_60min_confirm.py
- `weekly_smc_trend(weekly)` — 
- `daily_to_weekly(daily)` — 
- `detect_LD_sequences(signals)` — 
- `run_trades(ohlcv, sequences, signals, swings_dict)` — T+1 backtest returning trades
- `check_60min_support(daily_sig_date, daily_sig_bar, ohlcv_60min, sigs_60min)` — Check if 60min shows supporting bull signals before daily bar
- `summary(trades, label)` — 

## hermes\scripts\v11\backtest_compare.py
- `load_kline(code)` — 
- `_quick_swing_highs(ohlcv, lookback)` — 
- `extract_entries(sigs, ohlcv)` — Get bull signal entries from either V11 or V12 signal format.
- `backtest_stock(ohlcv, code, adaptive)` — 
- `main()` — 

## hermes\scripts\v11\backtest_final_v33.py
- `daily_to_weekly(daily)` — 
- `weekly_smc(weekly)` — 
- `detect_sequences(signals)` — 
- `backtest(ohlcv, seqs, start, target, lookahead)` — 

## hermes\scripts\v11\backtest_multitf_v37.py
- `load_ohlcv(symbol)` — 
- `load_60min_ohlcv(symbol, force_refresh)` — Load 60min data for a symbol, using cache or fetching from Tencent API.
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_atr(ohlcv, idx, period)` — 
- `find_all_swing_lows(ohlcv, end_idx, lookback)` — 
- `find_best_swing_sl(ohlcv, end_idx, entry_price)` — 
- `find_swing_high_forward(ohlcv, start_idx, lookahead)` — 
- `calc_structural_sl(ohlcv, entry_idx, entry_price, signal, all_signals)` — 
- `calc_structural_tp(ohlcv, entry_idx, entry_price, signal, all_signals)` — 
- `calc_trailing_v36(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — 
- `find_60min_index_for_daily(daily_t, ohlcv_60min)` — Find the index in 60min data corresponding to the daily bar date.
- `check_60min_support(daily_signal, daily_ohlcv, ohlcv_60min, signals_60min, lookback_60)` — Check if the 60min timeframe supports a daily bull signal.
- `find_overlap_start(daily_ohlcv, ohlcv_60min)` — Find first daily index that overlaps with 60min data range.
- `evaluate_signal_entry(ohlcv, sig_idx, sig, all_sigs_up_to_idx, all_signals, params)` — V36 entry evaluation, augmented with optional 60min confirmation.
- `backtest_stock_daily_only(ohlcv, symbol)` — V36 baseline: daily-only backtest.
- `backtest_stock_multitf(ohlcv, ohlcv_60min, symbol)` — Multi-TF backtest: daily data with 60min confirmation.
- `weekly_trend(weekly_data, lookback)` — Simple weekly trend detection for filter.
- `main()` — 
- `calc_aggregate(trades, stock_results)` — 

## hermes\scripts\v11\backtest_retrace_v62.py
- `summary(trades)` — 
- `execute_trade(daily, entry_bar, ep_in, tp, sl, sigs)` — Execute from entry_bar to exit. Returns trade dict or None.
- `run_backtest(files, method)` — method: 'open' = buy next bar open; 'retrace' = wait for retrace to zone

## hermes\scripts\v11\backtest_timerange.py
- `weekly_smc_trend(weekly)` — 
- `daily_to_weekly(daily)` — 
- `detect_LD_sequences(signals)` — 
- `run_trades(ohlcv, sequences, signals, swings_dict, date_range)` — T+1 backtest, filtered by date range
- `summary(trades, label)` — 

## hermes\scripts\v11\backtest_timerange_v5.py
- `weekly_smc_trend(weekly)` — 
- `daily_to_weekly(daily)` — 
- `detect_fvg_fills(daily)` — Calculate FVG回补率 for market state
- `market_state(fill_count, fvg_count)` — 
- `gather_v5_candidates(daily, sigs, sbb, w_trend, swings_dict)` — V5: L1 OB_Bull always + L2 ALL→ZONE in MeanReversion
- `run_trades(ohlcv, candidates, signals, swings_dict, date_range)` — 
- `summary(trades, label)` — 

## hermes\scripts\v11\backtest_v11.py
- 类: TradeRecord
- `backtest_single_stock_v11(ohlcv, symbol, params, tf, min_resonance, min_rr)` — 单股票V11回测
- `calc_trade_stats(trades)` — 计算交易统计
- `batch_backtest_v11(symbol_list, params, interval, bars, label, max_concurrent)` — 批量回测 — 全量验证
- `save_backtest_results(results, name)` — 保存回测结果
- `test_single(symbol, interval)` — 测试单股票回测
- `pnl(self)` — 盈亏点数

## hermes\scripts\v11\backtest_v37_core.py
- `load_ohlcv(symbol)` — 
- `calc_atr(ohlcv, idx, period)` — 
- `find_swing_lows(ohlcv, end_idx, lookback)` — 
- `find_best_swing_sl(ohlcv, end_idx, entry_price)` — 
- `calc_trailing_v36(entry_price, current_price, direction)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_weekly_context(ohlcv, idx)` — 周线上下文 — 方向 + 价格位置
- `score_entry_v37(all_signals, liquidity_result, weekly_ctx, idx, direction)` — V37综合入场评分
- `backtest_stock_v37(symbol, ohlcv)` — 单只股票V37回测
- `run_batch(symbols, limit)` — 

## hermes\scripts\v11\backtest_v5_full.py
- `weekly_smc_trend(weekly)` — 
- `daily_to_weekly(daily)` — 
- `get_market_state(fvg_fill_count, fvg_total)` — 基于FVG回补率判断市场状态
- `summarize(d, label)` — 

## hermes\scripts\v11\backtest_v62_full.py
- `detect_pinbars(daily)` — 
- `summary(trades)` — 

## hermes\scripts\v11\backtest_v63_full.py
- `load_ohlcv(symbol)` — 
- `load_weekly(symbol)` — 加载周线, 如果存在
- `check_weekly_bull(weekly, zone_bar_date)` — 检查周线是否Bull共振: 周线MA20上方>2%
- `calc_atr(daily, length)` — 
- `execute_trade(daily, pick, config, n, signal_cache, weekly)` — V7.6: ATR自适应参数
- `summary(trades)` — 

## hermes\scripts\v11\batch_backtest.py
- `load_ohlcv(symbol, period, count)` — Load cached OHLCV with format compatibility
- `simulate_trade(ohlcv, entry_idx, direction, sl_price, tp_price, max_hold)` — Simulate a trade from entry_idx+1 until SL/TP hit or max_hold bars
- `calc_pnl(entry_price, exit_price, direction)` — Calculate P&L percentage
- `calc_rr(entry_price, sl_price, tp_price, direction)` — Calculate expected risk/reward ratio
- `backtest_stock(ohlcv, symbol)` — Run V11 backtest on one stock — single-shot + forward simulation
- `main()` — 

## hermes\scripts\v11\check_sym_match.py

## hermes\scripts\v11\check_tiers.py

## hermes\scripts\v11\choch_compare.py

## hermes\scripts\v11\combo_filter_backtest.py
- `stats(r)` — 

## hermes\scripts\v11\combo_validation_v40.py
- `daily_to_weekly(daily)` — 
- `weekly_smc(weekly)` — 
- `analyze_stock(ohlcv, sym)` — Analyze one stock: test all combos across 3 windows

## hermes\scripts\v11\compare_v468_v469.py

## hermes\scripts\v11\cross_cycle_window_backtest.py
- `daily_to_weekly(daily)` — 
- `weekly_smc(weekly)` — 
- `detect_sequences(signals)` — 
- `backtest(ohlcv, seqs, start)` — 

## hermes\scripts\v11\cross_validate_v80.py
- `load_ohlcv(symbol)` — 
- `calc_atr(daily, length)` — 
- `sim_trade(daily, entry_bar, zone_low, entry_mode)` — 单笔快速模拟
- `agg(pnls)` — 

## hermes\scripts\v11\cross_validate_v81.py
- `load_ohlcv(sym)` — 
- `load_weekly(sym)` — 
- `calc_atr(daily, l)` — 
- `sim(daily, eb, zl, em)` — 
- `agg(pnls)` — 

## hermes\scripts\v11\data_loader.py
- `load_cached_ohlcv(symbol, interval, bars)` — Load & normalize cached OHLCV data — handles all cache formats
- `get_backtest_universe()` — Get symbols from cache files

## hermes\scripts\v11\decompose_v112.py
- `dw(d)` — 
- `wt(w)` — 
- `ds(signals)` — 
- `bt(ohlcv, seqs)` — 

## hermes\scripts\v11\detailed_trades_v60.py
- `fmt_date(d)` — 
- `daily_to_weekly(daily)` — 
- `weekly_smc(weekly)` — 
- `detect_sequences(signals)` — 
- `backtest_with_exit_detail(ohlcv, dates, seqs, start)` — Full trade simulation with exit reason tracking
- `_find_swings(ohlcv)` — Simple swing detection for TP targeting

## hermes\scripts\v11\diag_data.py

## hermes\scripts\v11\diag_entry.py

## hermes\scripts\v11\diag_signals.py

## hermes\scripts\v11\diag_v468_20.py

## hermes\scripts\v11\download_60min_all.py
- `symbol_to_tencent(symbol)` — 
- `fetch_60min_kline(symbol)` — 

## hermes\scripts\v11\download_weekly_v2.py
- `sym_to_secid(symbol)` — 600519.SH -> 1.600519, 000001.SZ -> 0.000001
- `download_weekly(symbol)` — 
- `main()` — 

## hermes\scripts\v11\download_weekly_v3.py
- `download_weekly(symbol)` — 
- `main()` — 

## hermes\scripts\v11\entry_at_zone_v50.py
- `daily_to_weekly(daily)` — 
- `weekly_smc(weekly)` — 
- `detect_sequences_with_zones(signals)` — Detect sequences AND extract zone info for entry
- `backtest_entry_at_zone(ohlcv, seqs, start)` — Test entry-at-zone: wait for pullback to zone, enter at close of that bar

## hermes\scripts\v11\entry_v17_backtest.py
- `run_entry_test(n_stocks)` — Run entry mode comparison on N stocks
- `_simulate_exit(ohlcv, entry_bar, entry_price, sl_price, tp_price, direction)` — Simulate exit: walk forward from entry_bar+1, check SL/TP hit

## hermes\scripts\v11\extract_params.py

## hermes\scripts\v11\failure_rolling_v10.py
- `daily_to_weekly(d)` — 
- `weekly_trend(w)` — 
- `detect_sequences(signals)` — 
- `backtest_window(ohlcv, seqs, window_start, window_end)` — Backtest within a specific bar range

## hermes\scripts\v11\fill_missing_stocks.py
- `download_daily(code, info)` — 

## hermes\scripts\v11\find_top20.py

## hermes\scripts\v11\free_combo_mining.py

## hermes\scripts\v11\full_backtest_v20.py
- `compute_stats(data)` — 

## hermes\scripts\v11\full_backtest_v4.py
- `detect_sequences(signals)` — 
- `weekly_smc_trend(weekly)` — 周线SMC趋势: CHOCH/BOS方向
- `simple_weekly_trend(weekly)` — 简易周线趋势: MA20方向
- `backtest_trades(ohlcv, sequences, weekly_trend, signals, swings_dict, start_bar)` — T+1交易回测，从start_bar开始
- `summary(trades, label)` — 
- `run_window(ohlcv, weekly, sequences, signals, swings_dict, w_trend)` — 在指定窗口运行回测

## hermes\scripts\v11\full_sequence_backtest_v70.py
- `detect_sequences(signals)` — Detect ALL sequence patterns from signal stream
- `backtest_sequences(ohlcv, seqs)` — T+1 close entry, 2% target in 5 bars
- `daily_to_weekly(daily)` — 
- `weekly_smc(weekly)` — 

## hermes\scripts\v11\future_function_audit.py

## hermes\scripts\v11\fvg_sl_opt.py

## hermes\scripts\v11\grid_search_v63.py
- `get_zone_entry(ob, daily, i, zone_def)` — Calculate zone entry price based on definition
- `summary(trades)` — 
- `detect_pinbars(daily)` — 
- `score_func(s)` — 

## hermes\scripts\v11\honest_report.py
- `weekly_trend_simple(daily)` — 

## hermes\scripts\v11\klines_60min.py
- `get_60min_kline(symbol, count)` — Download 60min K-line from Tencent ifzq API.
- `cache_60min(symbol, count)` — 

## hermes\scripts\v11\l2_combo_backtest_v6.py
- `detect_pinbars(daily)` — 
- `weekly_trend(weekly)` — 
- `daily_to_weekly(daily)` — 
- `summary(trades)` — 

## hermes\scripts\v11\liquidity_v37.py
- 类: LiquidityZone, LiquiditySignal
- `detect_liquidity_zones(ohlcv, swing_lookback, cluster_window, zone_merge_dist, tf)` — 检测流动性区域和猎杀事件
- `_cluster_swings(swings, max_dist, merge_price_pct, zone_type)` — 聚类摆动点 → 流动性区域
- `_make_zone(cluster, zone_type)` — 从聚类创建流动性区域
- `calc_adaptive_windows_v37(ohlcv)` — 根据波动率计算自适应信号序列窗口
- `enhance_signals_with_liquidity(all_signals, ohlcv)` — 用流动性信息增强现有V11信号
- `to_dict(self)` — 
- `to_dict(self)` — 

## hermes\scripts\v11\live_monitor.py
- `scan_recent_signals(picks_file, top_n)` — 扫描精选股票的最新信号
- `generate_signal_report()` — 生成监控报告

## hermes\scripts\v11\live_monitor_v21.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `find_all_swing_lows(ohlcv, end_idx, lookback)` — 
- `find_all_swing_highs(ohlcv, end_idx, lookback)` — 
- `find_best_swing_sl(ohlcv, end_idx, entry_price)` — 
- `find_best_swing_tp(ohlcv, end_idx, entry_price, sl_price)` — 
- `calc_sltp(ohlcv, end_idx, entry_price, signal_type)` — 
- `analyze_current_signals(ohlcv, symbol)` — V21: 在最新数据上检测可交易信号
- `main()` — 

## hermes\scripts\v11\live_pick_v1.py
- `refresh_one(symbol)` — Download latest daily bars from Hubble
- `refresh_all(max_workers)` — Refresh all stocks, skip already-fresh ones
- `load_dna()` — 
- `scan_today()` — Scan all stocks for active signals on the last bar

## hermes\scripts\v11\monitor_check.py
- `init_positions()` — 
- `check_exits()` — 

## hermes\scripts\v11\monitor_scanner.py
- `daily_to_weekly(daily)` — 
- `weekly_smc(weekly)` — 
- `parse_combo(combo_str)` — Parse combo string like "['FVG_Bear']" to set of types
- `scan_stock(sym, ohlcv, best_combos)` — Check if stock's best combo is currently active
- `main()` — 

## hermes\scripts\v11\multi_source_downloader.py
- `sym_to_eastmoney(symbol)` — 000001.SZ -> 0.000001, 600519.SH -> 1.600519
- `sym_to_tencent(symbol)` — 000001.SZ -> sz000001, 600519.SH -> sh600519
- `fetch_hubble_weekly(symbol)` — 
- `fetch_eastmoney_weekly(symbol)` — 
- `fetch_tencent_60min(symbol)` — 
- `download_weekly(symbol)` — 
- `download_60min(symbol)` — 
- `main()` — 

## hermes\scripts\v11\multi_tf_analyzer.py
- `download_weekly(symbol_raw)` — 下载单只股票周线. symbol_raw = '600519_SH'
- `weekly_trend(weekly_klines)` — 周线趋势: MA20斜率 + 价格位置.
- `detect_daily_sequences(signals, active_patterns)` — 检测日线上的SMC序列组合.
- `load_60min(symbol_raw)` — 加载60min数据.
- `test_sequence_performance(ohlcv, sequences)` — 测试每个序列的后续表现.

## hermes\scripts\v11\multi_tf_full_backtest_v32.py
- `daily_to_weekly(daily)` — 
- `weekly_smc(weekly)` — 
- `detect_sequences(signals)` — 
- `backtest(ohlcv, seqs, start)` — 

## hermes\scripts\v11\multi_tf_v2.py
- `daily_to_weekly(daily_ohlcv)` — 日线合成周线OHLC.
- `weekly_smc_trend(weekly_ohlcv)` — 周线SMC趋势: CHOCH/BOS方向 + 摆动结构.
- `detect_sequences(signals)` — 检测所有序列组合 (去重按entry_bar).
- `test_sequences(ohlcv, sequences, start_bar)` — 测试序列在未来N bar的命中率.

## hermes\scripts\v11\multi_tf_v2_final.py
- `daily_to_weekly(daily)` — 
- `weekly_smc(weekly)` — 
- `detect_sequences(signals)` — 
- `test(ohlcv, seqs, start)` — 

## hermes\scripts\v11\multitf_filter.py
- `get_weekly_trend(symbol)` — Determine weekly trend: bullish (>MA20), bearish (<MA20), or neutral.
- `get_daily_entries_with_weekly_filter(symbol, daily_signals, ohlcv)` — Filter daily entry signals by weekly trend.
- `refine_entry_60min(symbol, daily_entry_idx, entry_price, ohlcv_daily)` — Use 60min data to find better entry price.

## hermes\scripts\v11\ob_ctx_backtest_v6.py
- `detect_pinbars(daily)` — 
- `weekly_trend(weekly)` — 
- `daily_to_weekly(daily)` — 
- `summary(trades)` — 

## hermes\scripts\v11\ob_only_v111.py
- `daily_to_weekly(d)` — 
- `weekly_trend(w)` — 
- `detect_sequences(signals)` — 
- `bt(ohlcv, seqs)` — 

## hermes\scripts\v11\optimizer_v11.py
- `calc_opt_score(stats)` — 优化目标评分
- `optimize_single_stock(ohlcv, symbol, tf, iterations, seed_params)` — 单股票参数优化 — 局部搜索
- `_mutate_params(params, temperature)` — 对参数做随机扰动
- `batch_optimize_v11(symbol_list, tf, iters_per_stock, label, on_progress)` — 批量优化 — 每只股票独立搜索
- `save_optimizer_state(results, label)` — 保存优化中间状态
- `load_optimizer_state(label)` — 加载已保存的优化状态
- `validate_optimized(symbol_list, optimized_params, tf, label)` — 用优化后的参数进行全量回测验证

## hermes\scripts\v11\param_optimizer_v38.py
- 类: StockCache
- `patched_calc_sl(ohlcv, entry_idx, entry_price, signal, entry_type, structure_tree)` — ATR adaptive SL using CUSTOM_SL_MULT. Structural SL still takes priority.
- `patched_calc_tp(ohlcv, entry_idx, entry_price, signal, entry_type, structure_tree)` — TP using CUSTOM_TP_MULT scaling. Falls back to ATR-based TP.
- `evaluate_entry_with_params(cache, sig, direction)` — Evaluate a single entry with current CUSTOM_SL_MULT / CUSTOM_TP_MULT.
- `run_cached_backtest(cache)` — Run full backtest on cached stock data with current multipliers.
- `build_cache(symbol, ohlcv)` — Build cache for one stock, return None if invalid.
- `run_config_on_caches(caches, sl_mult, tp_mult)` — Run backtest with given multipliers on pre-built caches.
- `prebuild_caches(symbols, max_stocks)` — Build caches for all symbols (signals/tree/Wyckoff once).
- `phase1_grid(caches)` — Grid search: iterate SL_GRID × TP_GRID, find best global combo.
- `phase2_per_stock(caches)` — Find optimal SL/TP per stock.
- `main()` — 

## hermes\scripts\v11\per_stock_mining.py

## hermes\scripts\v11\per_stock_v62.py
- `detect_pinbars(daily)` — 

## hermes\scripts\v11\per_stock_v71.py
- `weekly_trend_simple(daily)` — 简化周线趋势: 最近20日MA vs 50日MA

## hermes\scripts\v11\portfolio_v40.py
- `quality_score(wr, rr)` — WR+RR → 仓位乘数
- `simulate_portfolio_pnl(trades_with_stock)` — 组合P&L蒙特卡洛模拟 (加性模型, bootstrapping)
- `main()` — 

## hermes\scripts\v11\quick_pick.py

## hermes\scripts\v11\rate_limiter.py
- 类: TokenBucket, ConcurrencyGuard, RequestCache, HubbleRateLimiter
- `get_limiter(max_rps, max_concurrent)` — 获取全局限流器单例
- `consume(self, tokens, timeout)` — 尝试消费令牌, 阻塞等待直到有令牌或超时
- `available(self)` — 当前可用令牌数
- `active(self)` — 
- `acquire(self, timeout)` — 
- `release(self)` — 
- `_key(self, url, params)` — 
- `get(self, url, params)` — 
- `put(self, url, params, data)` — 
- `size(self)` — 
- `hit_rate(self)` — 
- `_api_url(self, endpoint)` — 
- `_headers(self)` — 
- `_request(self, method, endpoint, params, timeout)` — 执行一个限流+退避的API请求
- `fetch_kline(self, symbol, interval, count, use_file_cache)` — 获取K线数据(限流+缓存)
- `batch_fetch(self, requests_list, batch_size, batch_delay, progress_cb)` — 批量获取K线数据(自动分批+节流)
- `get_stats(self)` — 获取限流统计
- `reset_stats(self)` — 重置统计

## hermes\scripts\v11\resonance_v11.py
- 类: ResonanceResult
- `calc_tf_resonance(tf_sequences, tf_data)` — 计算TF共振得分
- `calc_indicator_resonance(all_signals, last_n)` — 计算指标共振得分
- `_find_last_swing(ohlcv, left, right, name)` — 找最近的一个完整摆动点 — 从右向左扫描
- `calc_swing_resonance(ohlcv)` — 计算摆动点共振得分
- `calc_temporal_resonance(all_signals, last_n)` — 计算时间共振得分
- `evaluate_full_resonance_v11(all_signals, tf_sequences, tf_data, ohlcv)` — V11完整共振评估
- `make_entry_decision_v11(resonance, seq_result, params, tf_sequences)` — 基于共振+序列的综合入场决策
- `quick_analyze_v11(ohlcv, params, tf)` — 一键分析: 信号检测 → 序列分析 → 共振评分 → 入场决策
- `total(self)` — 加权总分
- `layers_active(self)` — 活跃层数 (>0.5)
- `grade(self)` — 
- `expected_wr(self)` — 
- `to_dict(self)` — 
- `coverage(signals)` — 

## hermes\scripts\v11\rolling_backtest.py
- `load_ohlcv(symbol)` — 
- `analyze_at_point(ohlcv, all_signals, end_idx, params, tf)` — Analyze signals up to end_idx and make entry decision
- `simulate_exit(ohlcv, entry_idx, direction, sl, tp, max_hold)` — Simulate trade exit
- `run_backtest(ohlcv, symbol, sl_pct, tp_pct, verbose)` — Run rolling backtest with given SL/TP params
- `scan_params(ohlcv, symbol, verbose)` — Find optimal SL/TP for this stock
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v114.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `get_entry_signal_info(seq_result)` — 从seq_result中正确提取入场信号信息
- `analyze_at_point_v114(ohlcv, all_signals, end_idx, params)` — V11.4分析: Scout + 紧窗口Silver/Bronze
- `simulate_trades(ohlcv, all_signals, params)` — 
- `backtest_stock(ohlcv, symbol)` — 
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v115.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `get_entry_signal_info(seq_result)` — 从seq_result中正确提取入场信号信息
- `analyze_at_point(ohlcv, all_signals, end_idx, params)` — 
- `simulate_trades(ohlcv, all_signals, params)` — 
- `backtest_stock(ohlcv, symbol)` — 
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v116.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `find_nearest_swing_low(ohlcv, end_idx, lookback)` — 找入场前最近的摆动低点(SL用)
- `find_nearest_swing_high(ohlcv, end_idx, lookback)` — 找入场前最近的摆动高点(TP用)
- `calc_swing_sltp(ohlcv, end_idx, entry_price)` — 基于摆动点计算SL和TP
- `get_entry_signal_info(seq_result)` — 
- `analyze_at_point(ohlcv, all_signals, end_idx, params)` — 
- `simulate_trades(ohlcv, all_signals, params)` — 
- `backtest_stock(ohlcv, symbol)` — 
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v117.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `find_best_swing_sl(ohlcv, end_idx, entry_price, lookback)` — 找距离最接近0.3-0.5%的摆动低点
- `find_best_swing_tp(ohlcv, end_idx, entry_price, sl_price, lookback)` — 找最近摆动高点作为TP，确保RR>=2.0x
- `calc_swing_sltp_v2(ohlcv, end_idx, entry_price)` — V11.7 摆动点SL/TP: 黄金约束
- `get_entry_signal_info(seq_result)` — 
- `analyze_at_point(ohlcv, all_signals, end_idx, params)` — 
- `simulate_trades(ohlcv, all_signals, params)` — 
- `backtest_stock(ohlcv, symbol)` — 
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v12.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `find_nearest_swing_low(ohlcv, end_idx, lookback)` — 找入场前最近的摆动低点
- `find_nearest_swing_high(ohlcv, end_idx, lookback)` — 找入场前最近的摆动高点
- `calc_swing_sltp_v12(ohlcv, end_idx, entry_price)` — V12 摆动点SL/TP: V11.6黄金公式
- `get_entry_signal_info(seq_result)` — 
- `score_signal_pattern(ohlcv, all_signals, end_idx)` — V12: 信号序列模式评分
- `analyze_at_point_v12(ohlcv, all_signals, end_idx, params)` — V12: 分析入场点 — Scout-only + 信号模式 + 多TF
- `simulate_trades_v12(ohlcv, all_signals, params)` — 
- `backtest_stock_v12(ohlcv, symbol)` — 
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v13.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `find_nearest_swing_low(ohlcv, end_idx, lookback)` — 找入场前最近的摆动低点 — 扩展lookback
- `find_nearest_swing_high(ohlcv, end_idx, lookback)` — 找入场前最近的摆动高点
- `calc_swing_sltp_v13(ohlcv, end_idx, entry_price, signal_type)` — V13 摆动点SL/TP:
- `get_entry_signal_info(seq_result)` — 
- `analyze_at_point_v13(ohlcv, all_signals, end_idx, params)` — V13: 分析入场点 — 扩展摆动+OB过滤
- `simulate_trades_v13(ohlcv, all_signals, params)` — 
- `backtest_stock_v13(ohlcv, symbol)` — 
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v14.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `find_all_swing_lows(ohlcv, end_idx, lookback)` — 找所有摆动低点, 返回[(idx, price, dist), ...]
- `find_all_swing_highs(ohlcv, end_idx, lookback)` — 找所有摆动高点
- `find_best_swing_sl(ohlcv, end_idx, entry_price, lookback)` — V14: 找最佳摆动SL — 不取最近, 取最接近0.5%的
- `find_best_swing_tp(ohlcv, end_idx, entry_price, sl_price, lookback)` — V14: 找最佳摆动TP
- `calc_swing_sltp_v14(ohlcv, end_idx, entry_price, signal_type)` — V14: 摆动+固定SL混合策略
- `get_entry_signal_info(seq_result)` — 
- `analyze_at_point(ohlcv, all_signals, end_idx, params)` — 
- `simulate_trades(ohlcv, all_signals, params)` — 
- `backtest_stock(ohlcv, symbol)` — 
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v15.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `find_all_swing_lows(ohlcv, end_idx, lookback)` — 
- `find_all_swing_highs(ohlcv, end_idx, lookback)` — 
- `find_best_swing_sl(ohlcv, end_idx, entry_price, max_dist)` — V15: 找20K线内的最佳摆动SL
- `find_best_swing_tp(ohlcv, end_idx, entry_price, sl_price, max_dist)` — 
- `calc_swing_sltp_v15(ohlcv, end_idx, entry_price, signal_type)` — V15: 距离约束摆动SL/TP
- `get_entry_signal_info(seq_result)` — 
- `analyze_at_point(ohlcv, all_signals, end_idx, params)` — 
- `simulate_trades(ohlcv, all_signals, params)` — 
- `backtest_stock(ohlcv, symbol)` — 
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v17.py
- `load_ohlcv(symbol)` — 
- `load_60min(symbol)` — Load 60min data from akshare cache
- `short_trend(ohlcv, idx, lookback)` — 
- `find_all_swing_lows(ohlcv, end_idx, lookback)` — 
- `find_all_swing_highs(ohlcv, end_idx, lookback)` — 
- `find_best_swing_sl(ohlcv, end_idx, entry_price, sl_cap, max_dist)` — 
- `find_best_swing_tp(ohlcv, end_idx, entry_price, sl_price, max_dist)` — 
- `calc_sltp(ohlcv, end_idx, entry_price, signal_type)` — 
- `get_entry_signal_info(seq_result)` — 
- `check_60min_before_daily_entry(daily_bar_date, min60_data, daily_sigs_before_entry)` — V17: 检查日线入场前, 60min是否有提前信号
- `analyze_at_point(ohlcv, min60_data, all_signals, end_idx, params)` — 
- `simulate_trades(ohlcv, min60_data, all_signals, params)` — 
- `backtest_stock(ohlcv, symbol)` — 
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v18.py
- `score_signal_sequence(sigs_before, entry_signal_type)` — V18: 基于信号序列模式评分
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `find_all_swing_lows(ohlcv, end_idx, lookback)` — 
- `find_all_swing_highs(ohlcv, end_idx, lookback)` — 
- `find_best_swing_sl(ohlcv, end_idx, entry_price, max_dist)` — 
- `find_best_swing_tp(ohlcv, end_idx, entry_price, sl_price, max_dist)` — 
- `calc_sltp(ohlcv, end_idx, entry_price, signal_type, sl_fixed, tp_fixed)` — 
- `get_entry_signal_info(seq_result)` — 
- `analyze_at_point(ohlcv, all_signals, end_idx, params, signal_seq_filter)` — 
- `simulate_trades(ohlcv, all_signals, params, sl_fixed, tp_fixed, signal_seq_filter)` — 
- `backtest_stock(ohlcv, symbol, sl_fixed, tp_fixed, signal_seq_filter)` — 
- `per_stock_optimize(ohlcv, symbol)` — V18: 每股SL/TP参数优化
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v19.py
- `load_phase_params(phase)` — Get parameters for a specific market phase
- `load_ohlcv(symbol)` — 
- `score_signal_sequence(sigs_before)` — V18 signal sequence scoring
- `short_trend(ohlcv, idx, lookback)` — 
- `find_all_swing_lows(ohlcv, end_idx, lookback)` — 
- `find_all_swing_highs(ohlcv, end_idx, lookback)` — 
- `find_best_swing_sl(ohlcv, end_idx, entry_price, sl_cap, max_dist)` — 
- `find_best_swing_tp(ohlcv, end_idx, entry_price, sl_price, max_dist)` — 
- `calc_sltp(ohlcv, end_idx, entry_price, signal_type, sl_fixed, tp_fixed)` — 
- `get_entry_signal_info(seq_result)` — 
- `analyze_at_point(ohlcv, all_signals, end_idx, params, phase_params)` — 
- `simulate_trades(ohlcv, all_signals, params, phase, symbol)` — 
- `backtest_stock(ohlcv, symbol)` — 
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v2.py
- `load_ohlcv(symbol)` — 
- `precompute_entries(ohlcv, all_signals, params)` — 预计算每个入场点的序列+共振信息
- `simulate_trades(ohlcv, entries, sl_pct, tp_pct)` — 使用预计算的entry candidates模拟交易
- `backtest_stock(ohlcv, symbol)` — Run full backtest with param scan on one stock
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v20.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `find_all_swing_lows(ohlcv, end_idx, lookback)` — 
- `find_all_swing_highs(ohlcv, end_idx, lookback)` — 
- `find_best_swing_sl(ohlcv, end_idx, entry_price, max_dist, sl_cap)` — 
- `find_best_swing_tp(ohlcv, end_idx, entry_price, sl_price, max_dist)` — 
- `calc_sltp(ohlcv, end_idx, entry_price, signal_type)` — 
- `get_entry_signal_info(seq_result)` — 
- `score_multi_cycle(ohlcv, idx)` — V20: 三级多周期评分 (微观/中观/宏观)
- `analyze_at_point(ohlcv, all_signals, end_idx, params, min_cycle_score)` — 
- `simulate_trades(ohlcv, all_signals, params, min_cycle)` — 
- `backtest_stock(ohlcv, symbol, min_cycle)` — 
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v22.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `find_all_swing_lows(ohlcv, end_idx, lookback)` — 
- `find_all_swing_highs(ohlcv, end_idx, lookback)` — 
- `find_best_swing_sl(ohlcv, end_idx, entry_price)` — 
- `find_best_swing_tp(ohlcv, end_idx, entry_price, sl_price)` — 
- `calc_sltp(ohlcv, end_idx, entry_price, signal_type)` — 
- `get_entry_signal_info(seq_result)` — 
- `score_signal_sequence(sigs_before, entry_signal_type)` — V22: 信号序列模式评分 (基于V18发现的真实WR数据)
- `analyze_at_point_v22(ohlcv, all_signals, end_idx, params)` — 
- `simulate_trades(ohlcv, all_signals, params)` — 
- `backtest_stock(ohlcv, symbol)` — 
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v23.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `find_all_swing_lows(ohlcv, end_idx, lookback)` — 
- `find_all_swing_highs(ohlcv, end_idx, lookback)` — 
- `find_best_swing_sl(ohlcv, end_idx, entry_price)` — 
- `find_best_swing_tp(ohlcv, end_idx, entry_price, sl_price, max_dist)` — 
- `calc_sltp_v23(ohlcv, end_idx, entry_price, signal_type, base_sl, base_tp)` — V23: Phase + Cycle adaptive SL/TP
- `get_entry_signal_info(seq_result)` — 
- `analyze_at_point(ohlcv, all_signals, end_idx, params, phase)` — 
- `simulate_trades_v23(ohlcv, all_signals, params, phase)` — 
- `backtest_stock_v23(ohlcv, symbol)` — 
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v24.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `find_all_swing_lows(ohlcv, end_idx, lookback)` — 
- `find_all_swing_highs(ohlcv, end_idx, lookback)` — 
- `find_best_swing_sl(ohlcv, end_idx, entry_price, max_dist, sl_cap)` — 
- `find_best_swing_tp(ohlcv, end_idx, entry_price, sl_price, max_dist)` — 
- `calc_sltp(ohlcv, end_idx, entry_price, signal_type, sl_fixed, tp_fixed)` — 
- `get_entry_signal_info(seq_result)` — 
- `simulate_trades(ohlcv, all_signals, params, phase, sl_fixed, tp_fixed)` — 
- `optimize_stock(ohlcv, symbol)` — V24: 对单股票找最优SL/TP组合
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v25.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `find_all_swing_lows(ohlcv, end_idx, lookback)` — 
- `find_all_swing_highs(ohlcv, end_idx, lookback)` — 
- `find_best_swing_sl(ohlcv, end_idx, entry_price)` — 
- `calc_initial_sl(ohlcv, end_idx, entry_price, signal_type, sl_fixed)` — 
- `calc_trailing_exit(ohlcv, entry_idx, entry_price, initial_sl, n, max_hold)` — V25: 追踪止盈退出
- `get_entry_signal_info(seq_result)` — 
- `simulate_trades(ohlcv, all_signals, params, phase)` — 
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v28.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `find_all_swing_lows(ohlcv, end_idx, lookback)` — V28: Wider lookback for swing low detection
- `find_best_swing_sl(ohlcv, end_idx, entry_price)` — V28: Wider SL range (0.10%-0.70%)
- `calc_initial_sl(ohlcv, end_idx, entry_price, signal_type, sl_fixed)` — 
- `calc_trailing_exit(ohlcv, entry_idx, entry_price, initial_sl, n, max_hold)` — V28: Smoother trailing with lower thresholds
- `evaluate_signal_entry(ohlcv, sig_idx, sig, all_sigs_up_to_idx, params, phase)` — V28: Uses confirmed_at for entry
- `backtest_stock_v28(ohlcv, symbol)` — 
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v3.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 检查短期趋势方向 — 用于Scout过滤
- `analyze_at_point(ohlcv, all_signals, end_idx, params, tf)` — 分析给定点的入场机会
- `simulate_trades(ohlcv, all_signals, params)` — 滚动回测: 检测入场点+模拟持仓
- `backtest_stock(ohlcv, symbol)` — 单股票回测+参数扫描
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v32.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `synthesize_weekly(ohlcv)` — 
- `weekly_trend(weekly, lookback)` — 
- `find_all_swing_lows(ohlcv, end_idx, lookback)` — 
- `find_best_swing_sl(ohlcv, end_idx, entry_price)` — 
- `calc_trailing_exit_v32(ohlcv, entry_idx, entry_price, initial_sl, n, max_hold)` — V32 trailing: +1.0% breakeven, +1.5% lock, +2.5% trail
- `score_signal_sequence(all_signals, target_signal)` — D) Signal time-sequence scoring — FIRST REAL IMPLEMENTATION
- `simulate_trades_v32(ohlcv, all_signals, params)` — V32 simulate with all fixes
- `run_stock(symbol)` — Run V32 on a single stock
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v33.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `synthesize_weekly(ohlcv)` — 
- `weekly_trend(weekly, lookback)` — 
- `find_all_swing_lows(ohlcv, end_idx, lookback)` — 
- `find_best_swing_sl(ohlcv, end_idx, entry_price)` — 
- `calc_trailing_v33(ohlcv, entry_idx, entry_price, initial_sl, n, max_hold)` — V28 tight trailing
- `run_stock_v33(symbol)` — V33: V28 core + signal timing scoring
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v34.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `synthesize_weekly(ohlcv)` — 
- `weekly_trend(weekly, lookback)` — 
- `find_all_swing_lows(ohlcv, end_idx, lookback)` — 
- `find_best_swing_sl(ohlcv, end_idx, entry_price)` — 
- `calc_trailing_v34(ohlcv, entry_idx, entry_price, initial_sl, n, max_hold)` — V28 tight trailing (identique)
- `run_stock_v34(symbol)` — V34: V28 core + V34 POI/timing scoring
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v35.py
- `load_ohlcv(symbol)` — 
- `synthesize_weekly(ohlcv)` — 合成周线数据
- `weekly_trend(weekly, lookback)` — 判断周线趋势 (多周期共振)
- `short_trend(ohlcv, idx, lookback)` — 短期趋势判断
- `find_all_swing_lows(ohlcv, end_idx, lookback)` — 找摆动低点 (支撑位)
- `find_all_swing_highs(ohlcv, end_idx, lookback)` — 找摆动高点 (阻力位)
- `find_best_swing_sl(ohlcv, end_idx, entry_price, sl_candidates)` — 摆动点SL — 找最近的摆动低点作为SL
- `find_swing_tp(ohlcv, end_idx, entry_price, lookback)` — 摆动点TP — 找最近的摆动高点作为初步TP
- `classify_signal_code(signal)` — 
- `_is_core_signal(signal)` — 
- `score_signal_v35(all_signals, target_signal, ohlcv, weekly_trend_val, phase, params)` — V35 4层信号评分:
- `calc_exit_v35(ohlcv, entry_idx, entry_price, sl_price, tp_price, max_hold)` — V35固定SL/TP退出:
- `run_stock_v35(symbol, sl_values, tp_values)` — V35单股票回测 — 支持多种SL/TP组合参数优化
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v351.py
- `load_ohlcv(symbol)` — 
- `synthesize_weekly(ohlcv)` — 
- `weekly_trend(weekly, lookback)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `find_all_swing_lows(ohlcv, end_idx, lookback)` — 
- `find_best_swing_sl(ohlcv, end_idx, entry_price)` — 
- `calc_trailing_v35(ohlcv, entry_idx, entry_price, initial_sl, n, max_hold)` — V35.1 trailing:
- `classify_signal_code(signal)` — 
- `_is_core_signal(signal)` — 
- `score_signal_v35(all_signals, target_signal, ohlcv, weekly_trend_val, phase, entry_bar_idx)` — V35.1 4层评分 — 在entry_bar_idx处评估
- `run_stock_v35(symbol)` — 
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v36.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_atr(ohlcv, idx, period)` — Simple ATR calculation for SL/TP volatility reference
- `find_all_swing_lows(ohlcv, end_idx, lookback)` — 
- `find_best_swing_sl(ohlcv, end_idx, entry_price)` — 
- `find_swing_high_forward(ohlcv, start_idx, lookahead)` — Find the first swing high AFTER start_idx
- `calc_structural_sl(ohlcv, entry_idx, entry_price, signal, all_signals)` — 基于SMC结构的止损计算
- `calc_structural_tp(ohlcv, entry_idx, entry_price, signal, all_signals)` — 基于SMC结构的止盈计算
- `calc_trailing_v36(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V36: 结构感知的trailing
- `evaluate_signal_entry(ohlcv, sig_idx, sig, all_sigs_up_to_idx, all_signals, params)` — V36: 使用结构SL/TP
- `backtest_stock_v36(ohlcv, symbol)` — 
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v37.py
- `load_ohlcv(symbol)` — 
- `calc_atr(ohlcv, idx, period)` — Simple ATR for volatility reference
- `find_swing_highs(ohlcv, lookback)` — 找摆动高点
- `find_swing_lows(ohlcv, lookback)` — 找摆动低点
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_weekly_resonance(ohlcv, idx)` — 计算周线上下文对日线信号的共振得分
- `classify_structure_shift(mss_signals, choch_signals, idx, direction)` — 对当前K线附近的结构变化做层级分类
- `score_v37_entry(all_signals, liquidity_result, weekly_res, structure_shift, adaptive_windows, ohlcv)` — V37综合入场评分 (v2 — 收紧版)
- `calc_structural_sl_v37(ohlcv, all_signals, entry_idx, entry_price, direction)` — V37增强结构SL
- `calc_structural_tp_v37(ohlcv, all_signals, entry_idx, entry_price, direction)` — V37结构TP
- `calc_trailing_v37(entry_price, current_price, sl_price, direction)` — V37增强trailing
- `evaluate_signal_entry_v37(ohlcv, idx, all_signals, liquidity_result, direction)` — V37 — ICT Liquidity Sweep + FVG 入场
- `backtest_stock_v37(symbol, ohlcv)` — 对单只股票运行V37回测
- `run_v37_batch(stock_list, limit)` — 批量运行V37回测

## hermes\scripts\v11\rolling_backtest_v38.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `find_entry_signal(all_signals, entry_bar, direction)` — 在entry_bar位置寻找可用入场信号
- `atr_grid_search(ohlcv, symbol, all_signals, structure_tree, wyckoff_result)` — 每股ATR网格搜索: 在SL_MULT×TP_MULT网格上搜索最优参数组合
- `calc_v38_sl(ohlcv, entry_idx, entry_price, signal, entry_type, structure_tree)` — V38结构SL计算 (3层优先级)
- `calc_v38_tp(ohlcv, entry_idx, entry_price, signal, entry_type, structure_tree)` — V38结构TP计算 (3层优先级)
- `calc_v38_trailing(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V38.4 差异化trailing:
- `evaluate_v38_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n, structure_tree)` — V38统一入场评估 (多入口类型 + 做空)
- `backtest_stock_v38(ohlcv, symbol)` — 单股票V38回测
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v6.py
- `load_ohlcv(symbol)` — 
- `detect_phase(ohlcv, idx)` — 检测当前市场阶段
- `ema_slope(ohlcv, idx, period)` — 计算EMA斜率（%变化）
- `avg_volume(ohlcv, idx, period)` — 计算平均成交量
- `bar_volume(ohlcv, idx)` — 
- `check_bar_close(ohlcv, idx, direction)` — 检查信号bar的收盘是否在预期方向
- `check_signal_quality(sig, ohlcv, signals_up_to_idx)` — 检查单个信号的质量
- `simulate_one_trade(ohlcv, entry_idx, sl_pct, tp_pct, direction)` — 模拟一笔交易
- `backtest_stock_v6(ohlcv, symbol)` — V6信号级回测
- `main()` — 

## hermes\scripts\v11\rolling_backtest_v7.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `analyze_at_point(ohlcv, all_signals, end_idx, params)` — 
- `simulate_trades(ohlcv, all_signals, params)` — 
- `backtest_stock(ohlcv, symbol)` — 
- `main()` — 

## hermes\scripts\v11\run_v38_full.py
- `run_full()` — 

## hermes\scripts\v11\run_v44_c.py

## hermes\scripts\v11\scan_LD_signals.py
- `weekly_smc_trend(weekly)` — 
- `daily_to_weekly(daily)` — 
- `detect_sequences(signals, direction)` — 

## hermes\scripts\v11\scan_LD_v2.py
- `weekly_smc_trend(weekly)` — 
- `daily_to_weekly(daily)` — 
- `detect_sequences_v2(signals)` — 改进版序列检测: OB优先 + min_gap + banned chains

## hermes\scripts\v11\scan_LD_v3.py
- `weekly_smc_trend(weekly)` — 
- `daily_to_weekly(daily)` — 
- `calc_sl_tp(entry_price, zone_signal, all_signals, swings_dict, daily)` — 计算SL/TP: SL=zone_low(cap 3%), TP=结构止盈or固定3%

## hermes\scripts\v11\scan_LD_v4.py
- `weekly_smc_trend(weekly)` — 
- `daily_to_weekly(daily)` — 
- `make_ob_pick(sym, ob_sig, entry_bar, entry_price, sl, tp)` — 
- `make_combo_pick(sym, liq_sig, fvg_sig, gap, entry_bar, entry_price)` — 

## hermes\scripts\v11\scan_LD_v5.py
- `weekly_smc_trend(weekly)` — 
- `daily_to_weekly(daily)` — 
- `detect_market_state(daily, signals, sbb)` — FVG回补率 = 最近20个FVG_Bull中被回补的比例
- `calc_signal_score(sym, signal_type, market_state, daily, signals, sbb)` — SignalScore ∈ [0, 1]
- `calc_position_size(strategy_weight, signal_score, risk_scaler)` — 
- `calc_risk_scaler(recent_trades)` — 基于最近20笔交易动态调整风险

## hermes\scripts\v11\scan_LD_v6.py
- `detect_pinbars(daily)` — SMC Pinbar: entry confirmation at PD Arrays (OB/FVG), NOT standalone zone.
- `detect_fvg_fills(daily)` — 
- `market_state(fill_c, fvg_c)` — 
- `calc_score(sym, signal_type, ms, ctx_count, gap)` — SignalScore [0, 1]
- `weekly_trend(weekly)` — 
- `daily_to_weekly(daily)` — 

## hermes\scripts\v11\scan_ab_quality_v25.py
- `cycle_filter_passes(seq_result)` — Multi-cycle filter: only allow sequences that are not BEARISH or 1UP2NEUTRAL
- `simulate_trades_v25(ohlcv, all_signals, params, phase, quality)` — V25 simulation with phase-adaptive SL/TP, multi-cycle filter, trailing stop exit.

## hermes\scripts\v11\scan_all_combos.py
- `weekly_trend_simple(weekly)` — 
- `daily_to_weekly(daily)` — 

## hermes\scripts\v11\scan_etf_v16.py
- `is_etf(symbol)` — 
- `scan_etfs()` — 

## hermes\scripts\v11\scan_full_market_v16.py
- `scan_batch(symbols, batch_id)` — Scan a batch of symbols
- `main()` — 

## hermes\scripts\v11\scan_full_market_v21.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `find_all_swing_lows(ohlcv, end_idx, lookback)` — 
- `find_all_swing_highs(ohlcv, end_idx, lookback)` — 
- `find_best_swing_sl(ohlcv, end_idx, entry_price)` — 
- `find_best_swing_tp(ohlcv, end_idx, entry_price, sl_price)` — 
- `calc_sltp(ohlcv, end_idx, entry_price, signal_type)` — 
- `get_entry_signal_info(seq_result)` — 
- `score_multi_cycle(ohlcv, idx)` — V20: 三级多周期评分
- `analyze_at_point(ohlcv, all_signals, end_idx, params)` — 
- `simulate_trades(ohlcv, all_signals, params)` — 
- `backtest_stock(ohlcv, symbol)` — 
- `scan_batch(symbols, batch_id)` — 
- `main()` — 

## hermes\scripts\v11\scan_full_market_v23.py
- `scan_batch(symbols, batch_id)` — 
- `main()` — 

## hermes\scripts\v11\scan_full_market_v23_v2.py

## hermes\scripts\v11\scan_full_market_v25.py

## hermes\scripts\v11\scan_full_market_v25_ab.py
- `simulate_trades_v25_ab(ohlcv, all_signals, params, phase)` — V25 with extra multi-cycle filter: skip BEARISH & 1UP2NEUTRAL

## hermes\scripts\v11\scan_full_market_v27.py

## hermes\scripts\v11\scan_full_market_v28.py

## hermes\scripts\v11\scan_full_market_v32.py

## hermes\scripts\v11\scan_full_market_v33.py

## hermes\scripts\v11\scan_full_market_v37.py

## hermes\scripts\v11\seq_comparison.py

## hermes\scripts\v11\sequencer_v11.py
- `normalize_signal(sig)` — 标准化信号类型为序列匹配可用的token
- `_find_fvg_entry(best_sequence, sequences_found)` — [V11.4] 若序列以OB结尾且前方有FVG, 返回FVG作为提前入场信号
- `match_sequence_with_temporal_weight(token_list, pattern, windows, min_steps)` — 时间加权的序列匹配
- `_same_family_v11(token, pattern_step)` — 检查两个信号是否属于同一族
- `analyze_sequence_v11(all_signals, params)` — V11序列分析主入口
- `multi_tf_sequence_v11(tf_results)` — 多周期序列分析
- `score_entry_v11(seq_result, resonance_result, base_score)` — 基于序列分析的入场评分
- `seq_score(s)` — 

## hermes\scripts\v11\signal_diag.py

## hermes\scripts\v11\signal_timing_sequencer_v11.py
- `classify_signal_code(signal)` — Convert a signal dict to its 1-char type code
- `_is_core_signal(signal)` — Check if this is a core SMC signal (not auxiliary)
- `extract_signal_chain(all_signals, target_bar, lookback, max_signals, direction, exclude_idx)` — 提取目标bar之前, 特定方向的信号链
- `score_chain_by_pattern(code_string, direction)` — Layer 2: 信号链模式评分
- `analyze_signal_cluster(all_signals, target_signal, direction)` — 分析目标信号周围的信号"集群" — 不仅仅是最近1个信号
- `score_signal_timing(all_signals, target_signal, params)` — 综合信号时序评分 — V33核心
- `_default_result(reason, score)` — 

## hermes\scripts\v11\signal_timing_sequencer_v34.py
- 类: POI
- `extract_poi_from_fvg(signal)` — 从FVG信号中提取POI区域
- `extract_poi_from_ob(signal)` — 从OB信号中提取POI区域
- `extract_poi_from_swing(ohlcv, end_idx, direction, lookback)` — 从摆动低点/高点提取POI
- `classify_price_context(ohlcv, current_idx, fvg_signal)` — 分析当前价格相对于FVG POI的位置和行为
- `extract_signal_chain_v34(all_signals, target_bar, lookback, max_signals, direction, exclude_idx)` — 从V33升级: 只提取小于target_bar的信号(严格前序)
- `_is_core_signal(signal)` — 
- `classify_signal_code(signal)` — 
- `score_chain_by_pattern(code_string, direction)` — V33模式匹配引擎
- `score_signal_v34(all_signals, fvg_signal, ohlcv, current_idx, params)` — V34完整评分: V33信号链 + V34 POI + 价格行为上下文
- `_grade_v34(score, context, pattern)` — V34分级逻辑 — 比V33更灵活
- `_default_result(reason, score)` — 
- `run_v34_diagnostics(symbol, all_signals, ohlcv)` — 对一只股票运行V34诊断
- `is_tested(self, bar, current_idx)` — 检查当前bar是否测试了POI
- `is_bounced(self)` — POI是否产生了有效反弹(确认)
- `value_score(self)` — POI的价值评分

## hermes\scripts\v11\signals_v11.py
- 类: Signal
- `calc_adaptive_thresholds(ohlcv)` — 基于数据自适应计算所有阈值
- `detect_fvg_v11(ohlcv, min_width, merge_dist, adaptive, tf)` — V11增强FVG检测
- `_classify_fvg_width(gap_pct, ohlcv, idx, adaptive)` — 基于ATR的FVG宽度分级
- `_check_trend_alignment(ohlcv, idx, direction, lookback)` — 检查FVG是否与局部趋势对齐
- `_calc_fvg_strength(sig, middle_candle, adaptive)` — FVG信号强度评分 (0-10)
- `_calc_fvg_confidence(sig, b1, b2, b3, gap_pct)` — FVG置信度 (0-1)
- `_merge_fvgs_v11(fvg_signals, max_gap)` — 合并相邻同向FVG
- `_detect_fvg_stacks_v11(signals, ohlcv)` — 检测FVG堆叠 — 3+个FVG重叠 → 极强区域
- `_trace_mitigation_v11(signals, ohlcv)` — 追踪FVG填充状态
- `detect_sweep_v11(ohlcv, lookback, wick_ratio, adaptive, require_volume, require_reversal)` — V11增强Sweep检测
- `_find_swing_highs(ohlcv, lookback)` — 找摆动高点列表 (idx, price)
- `_find_swing_lows(ohlcv, lookback)` — 找摆动低点列表 (idx, price)
- `_classify_wick(ratio)` — 影线比分级
- `_calc_sweep_strength(cur, wick, wick_ratio, wick_grade, adaptive, at_swing)` — Sweep信号强度 (0-10)
- `_calc_sweep_confidence(cur, wick_ratio, vol_ok, at_swing)` — Sweep置信度 (0-1)
- `detect_ob_v11(ohlcv, strength_min, adaptive, require_volume, tf)` — V11.2 True ICT Order Block Detection
- `_calc_ob_strength_v11(body_pct, volume, vol_median, adaptive)` — OB强度 (0-10)
- `_calc_ob_confidence_v11(body_pct, vol_ok, at_structure, impulse_bars)` — OB置信度 (0-1) — V11.2
- `_calc_ob_confidence(range_pct, volume, vol_median, confirm_candle)` — OB置信度 (0-1)
- `detect_choch_v11(ohlcv, lookback, min_confirm_bars, sweep_signals, tf)` — V11.3 ICT CHOCH检测 — 带流动性位置约束
- `_calc_choch_strength_v11(break_strength, confirm_count, lookback)` — CHOCH强度 (0-10) — V11.1
- `_calc_choch_confidence_v11(break_strength, confirm_count)` — CHOCH置信度 (0-1) — V11.1
- `detect_bpr_v11(ohlcv, fvg_signals, tf)` — BPR (Balanced Price Range) — 反向FVG的重叠区域
- `detect_liquidity_void_v11(ohlcv, min_gap_pct, tf)` — Liquidity Void — 真正的价格流动性真空 (跳空缺口)
- `detect_rejection_block_v11(ohlcv, min_wick_pct, min_reversal, tf)` — 拒绝块检测 — 价格触及某水平后强烈反转
- `detect_ifvg_v11(ohlcv, min_width, adaptive, tf)` — IFVG (Implied Fair Value Gap) — 影线中点隐含缺口
- `detect_mitigated_fvg_v11(ohlcv, fvg_signals, tf)` — FVG_Mitigated — 被填充的FVG反向变成支撑/阻力
- `detect_breaker_block_v11(ohlcv, choch_signals, ob_signals, fvg_signals, tf)` — BreakerBlock — CHOCH发生后，原OB被破坏变成反向的Breaker Block
- `detect_eql_v11(ohlcv, lookback, tolerance_pct, tf)` — EQL (Equal Highs/Lows) — 等高点/等低点支撑阻力
- `detect_ote_v11(ohlcv, swing_signals, tf)` — OTE (Optimal Trade Entry) — 斐波那契61.8%回撤最佳入场
- `detect_mss_v11(ohlcv, lookback, min_confirm, tf)` — MSS (Market Structure Shift) — 微观结构转变
- `detect_po3_v11(ohlcv, lookback, adaptive, tf)` — PO3 (Power of 3) — ICT Power of 3: 蓄势(ACC)->操纵(MAN)->分配(DIS)
- `detect_all_signals_v11(ohlcv, params, adaptive, tf)` — V11统一信号检测入口
- `to_dict(self)` — 
- `_near_swing(idx, price, is_high, window)` — Check if price is near a swing point within `window` bars of idx
- `_is_near_swing(idx, max_dist)` — 
- `_is_strong_impulse(start, direction, min_bars)` — Check for strong impulse after OB. Returns number of consecutive bars.
- `_is_above_sweep(idx, price, lookahead)` — Bull CHOCH必须在此之前的SSL sweep之上
- `_is_below_sweep(idx, price, lookahead)` — Bear CHOCH必须在此之前的BSL sweep之下

## hermes\scripts\v11\signals_v11_backup_v37.py
- 类: Signal
- `calc_adaptive_thresholds(ohlcv)` — 基于数据自适应计算所有阈值
- `detect_fvg_v11(ohlcv, min_width, merge_dist, adaptive, tf)` — V11增强FVG检测
- `_classify_fvg_width(gap_pct, ohlcv, idx, adaptive)` — 基于ATR的FVG宽度分级
- `_check_trend_alignment(ohlcv, idx, direction, lookback)` — 检查FVG是否与局部趋势对齐
- `_calc_fvg_strength(sig, middle_candle, adaptive)` — FVG信号强度评分 (0-10)
- `_calc_fvg_confidence(sig, b1, b2, b3, gap_pct)` — FVG置信度 (0-1)
- `_merge_fvgs_v11(fvg_signals, max_gap)` — 合并相邻同向FVG
- `_detect_fvg_stacks_v11(signals, ohlcv)` — 检测FVG堆叠 — 3+个FVG重叠 → 极强区域
- `_trace_mitigation_v11(signals, ohlcv)` — 追踪FVG填充状态
- `detect_sweep_v11(ohlcv, lookback, wick_ratio, adaptive, require_volume, require_reversal)` — V11增强Sweep检测
- `_find_swing_highs(ohlcv, lookback)` — 找摆动高点列表 (idx, price)
- `_find_swing_lows(ohlcv, lookback)` — 找摆动低点列表 (idx, price)
- `_classify_wick(ratio)` — 影线比分级
- `_calc_sweep_strength(cur, wick, wick_ratio, wick_grade, adaptive, at_swing)` — Sweep信号强度 (0-10)
- `_calc_sweep_confidence(cur, wick_ratio, vol_ok, at_swing)` — Sweep置信度 (0-1)
- `detect_ob_v11(ohlcv, strength_min, adaptive, require_volume, tf)` — V11.2 True ICT Order Block Detection
- `_calc_ob_strength_v11(body_pct, volume, vol_median, adaptive)` — OB强度 (0-10)
- `_calc_ob_confidence_v11(body_pct, vol_ok, at_structure, impulse_bars)` — OB置信度 (0-1) — V11.2
- `_calc_ob_confidence(range_pct, volume, vol_median, confirm_candle)` — OB置信度 (0-1)
- `detect_choch_v11(ohlcv, lookback, min_confirm_bars, tf)` — V11.1 精简CHOCH检测 — 只在真实摆动点检测结构转换
- `_calc_choch_strength_v11(break_strength, confirm_count, lookback)` — CHOCH强度 (0-10) — V11.1
- `_calc_choch_confidence_v11(break_strength, confirm_count)` — CHOCH置信度 (0-1) — V11.1
- `detect_bpr_v11(ohlcv, fvg_signals, tf)` — BPR (Balanced Price Range) — 价格回到FVG区域后的测试
- `detect_liquidity_void_v11(ohlcv, min_gap_pct, tf)` — Liquidity Void — 真正的价格流动性真空 (跳空缺口)
- `detect_rejection_block_v11(ohlcv, min_wick_pct, min_reversal, tf)` — 拒绝块检测 — 价格触及某水平后强烈反转
- `detect_ifvg_v11(ohlcv, fvg_signals, tf)` — IFVG (Inversion FVG) — 被填充的FVG反向变成支撑/阻力
- `detect_breaker_block_v11(ohlcv, choch_signals, ob_signals, tf)` — BreakerBlock — CHOCH发生后，原OB被破坏变成反向的Breaker Block
- `detect_eql_v11(ohlcv, lookback, tolerance_pct, tf)` — EQL (Equal Highs/Lows) — 等高点/等低点支撑阻力
- `detect_ote_v11(ohlcv, swing_signals, tf)` — OTE (Optimal Trade Entry) — 斐波那契61.8%回撤最佳入场
- `detect_mss_v11(ohlcv, lookback, min_confirm, tf)` — MSS (Market Structure Shift) — 微观结构转变
- `detect_po3_v11(ohlcv, lookback, adaptive, tf)` — PO3 (Power of 3) — ICT Power of 3: 蓄势(ACC)->操纵(MAN)->分配(DIS)
- `detect_all_signals_v11(ohlcv, params, adaptive, tf)` — V11统一信号检测入口
- `to_dict(self)` — 
- `_near_swing(idx, price, is_high, window)` — Check if price is near a swing point within `window` bars of idx
- `_is_near_swing(idx, max_dist)` — 
- `_is_strong_impulse(start, direction, min_bars)` — Check for strong impulse after OB. Returns number of consecutive bars.

## hermes\scripts\v11\signals_v12.py
- 类: Signal
- `calc_adaptive_thresholds(ohlcv)` — Calculate volatility-adaptive thresholds from OHLCV data.
- `detect_swings_v12(ohlcv, left, right, min_swing_pct, adaptive, vol_invert)` — Pine-equivalent swing detection with RIGHT CONFIRMATION.
- `detect_swings_v13_60min(ohlcv, left, right, adaptive)` — 60min-optimized swing detection — right=2, ATR=1.0x.
- `_quick_sh(ohlcv, lb)` — 
- `_quick_sl(ohlcv, lb)` — 
- `detect_ob_v12(ohlcv, strength_min, adaptive, require_volume, displacement_mult, swings)` — CORRECTED ICT Order Block detection using backward swing scan.
- `detect_structure_v12(ohlcv, swings, tf)` — State machine BOS/CHOCH detection.
- `detect_fvg_v12(ohlcv, min_width, merge_dist, adaptive, tf)` — FVG detection — maintained from V11.
- `_trend_ok(ohlcv, idx, direction)` — 
- `detect_sweep_v12(ohlcv, lookback, wick_ratio, adaptive, require_volume, require_reversal)` — Swing-point level sweep detection — fixed for signal correctness.
- `detect_eql_v12(ohlcv, threshold_pct, swings, tf)` — Pivot-based EQH/EQL — Pine Script UAlgo style.
- `detect_bpr_v12(ohlcv, fvg_signals, tf)` — BPR — Balanced Price Range (FVG overlap area), same as V11.
- `detect_liquidity_void_v12(ohlcv, min_gap_pct, tf)` — LV — Liquidity Void (gap), same as V11.
- `detect_rejection_block_v12(ohlcv, min_wick_pct, tf)` — RJ — Rejection Block (long wick), same as V11.
- `detect_ifvg_v12(ohlcv, min_width, adaptive, tf)` — IFVG — Implied FVG (wick midpoint gap), same as V11.
- `detect_mitigated_fvg_v12(ohlcv, fvg_signals, tf)` — Mitigated FVG — price returned to fill the gap, same as V11.
- `detect_breaker_block_v12(ohlcv, choch_signals, fvg_signals, tf)` — Breaker Block — CHOCH + previous OB area, same as V11.
- `detect_ote_v12(ohlcv, swing_signals, adaptive, tf)` — OTE — Optimal Trade Entry (61.8% Fibonacci retracement), same as V11.
- `detect_po3_v12(ohlcv, lookback, adaptive, tf)` — PO3 — Power of 3 (accumulation/manipulation/distribution), same as V11.
- `detect_mss_v12(ohlcv, lookback, tf)` — MSS — Micro Structure Shift (3-candle window for direction change).
- `detect_all_signals_v12(ohlcv, params, tf)` — Universal signal detection — drop-in replacement for V11 detect_all_signals_v11().
- `detect_ob_v13_60min(ohlcv, adaptive, swings, tf)` — 60min-optimized OB: swing-backward + aggressively relaxed forward fallback.
- `detect_all_signals_v13_60min(ohlcv, params, tf)` — V13 60min signal detection — uses 60min-optimized OB detection.
- `to_dict(self)` — 
- `_near_swing(idx, w)` — 
- `_find_between(sw, si, ei)` — 

## hermes\scripts\v11\signals_v14.py
- 类: Signal
- `calc_adaptive_thresholds(ohlcv)` — 计算基于数据的自适应阈值——复用V11
- `detect_swings_v14(ohlcv, left, right, atr_filter)` — Pine-style pivothigh/pivotlow
- `_classify_fvg_width(gap_pct, atr_pct)` — 
- `_check_trend_alignment(ohlcv, idx, direction, lookback)` — 
- `detect_fvg_v14(ohlcv, min_width, merge_dist, adaptive, tf)` — FVG检测 — 复用V11逻辑
- `_quick_swing_highs(ohlcv, lookback)` — 
- `_quick_swing_lows(ohlcv, lookback)` — 
- `detect_ob_v14(ohlcv, swings, displacement_mult, adaptive, tf)` — Pine-quality OB检测
- `_detect_trend_v14(ohlcv, idx, lookback)` — 快速趋势判断
- `detect_choch_v14(ohlcv, swings, lookback, min_confirm, tf)` — CHOCH检测 — 状态机
- `detect_sweep_v14(ohlcv, lookback, wick_ratio, adaptive, tf)` — Sweep检测 — 复用V11核心逻辑
- `detect_mss_v14(ohlcv, lookback, min_confirm, tf)` — MSS — 微结构转变 (复用V11)
- `detect_eql_v14(ohlcv, swings, tolerance_pct, tf)` — EQL检测 — 基于摆动点
- `detect_bpr_v14(ohlcv, fvg_signals, tf)` — BPR — 复用V11
- `detect_ifvg_v14(ohlcv, adaptive, tf)` — IFVG — 简化版, 复用V11核心
- `detect_all_signals_v14(ohlcv, params, adaptive, tf)` — V14统一信号检测入口
- `to_dict(self)` — 

## hermes\scripts\v11\signals_v15.py
- 类: Signal
- `calc_adaptive_thresholds(ohlcv)` — 
- `detect_swings_v15(ohlcv, left, right, atr_filter)` — Pine-equivalent pivothigh/pivotlow
- `_merge_same_direction(swings, ohlcv, is_high)` — Merge consecutive swings of same direction keeping the most extreme
- `_filter_tiny_swings(swings, min_amp, direction, ohlcv)` — Filter swings with amplitude < min_amp from previous opposite swing
- `detect_fvg_v15(ohlcv, adaptive, tf)` — Pine SMC 2026 exact:
- `_check_trend(ohlcv, idx, direction, lookback)` — 
- `detect_ob_v15(ohlcv, swings, displacement_mult, ob_lookback, adaptive, tf)` — Pine SMC 2026 exact OB detection:
- `detect_structure_v15(ohlcv, swings, tf)` — Pine SMC 2026 structure detection:
- `detect_mss_v15(ohlcv, swings, tf)` — MSS (Market Structure Shift) — early warning of structure change.
- `detect_sweep_v15(ohlcv, swings, tf)` — Sweep (Liquidity Grab): price briefly breaks a swing high/low
- `detect_eql_v15(ohlcv, swings, tolerance_pct, atr_val, tf)` — Pine SMC 2026 exact EQH/EQL:
- `detect_bpr_v15(ohlcv, fvg_signals, ob_signals, tf)` — BPR (Balanced Price Range): price zone where both bull and bear
- `detect_ifvg_v15(ohlcv, adaptive, tf)` — IFVG — 简化版
- `detect_all_signals_v15(ohlcv, params, adaptive, tf)` — V15 unified signal detection — Pine Script quality.
- `to_dict(self)` — 

## hermes\scripts\v11\signals_v16.py
- 类: Signal
- `calc_adaptive_thresholds(ohlcv)` — 
- `detect_swings_v16(ohlcv, left, right, atr_filter)` — Pine pivothigh/pivotlow with right confirmation.
- `_merge_consecutive(swings, ohlcv, is_high)` — 
- `_filter_tiny(swings, min_amp, ohlcv)` — 
- `detect_fvg_v16(ohlcv, adaptive, tf)` — 
- `_check_trend(ohlcv, idx, direction, lookback)` — 
- `detect_ob_v16(ohlcv, swings, displacement_mult, ob_lookback, adaptive, tf)` — 
- `detect_structure_v16(ohlcv, swings, tf)` — V15 BUG: last_swing_high = max(all_highs) → 需要突破全图最高才触发.
- `detect_mss_v16(ohlcv, swings, tf)` — 
- `detect_sweep_v16(ohlcv, swings, tf)` — 
- `detect_eql_v16(ohlcv, swings, tolerance_pct, atr_val, tf)` — V16 dual-mode EQL:
- `detect_bpr_v16(ohlcv, fvg_signals, ob_signals, tf)` — 
- `detect_ifvg_v16(ohlcv, adaptive, tf)` — 
- `detect_all_signals_v16(ohlcv, params, adaptive, tf)` — 
- `to_dict(self)` — 

## hermes\scripts\v11\signals_v17.py
- 类: Signal
- `calc_adaptive_thresholds(ohlcv)` — 
- `detect_consensus_swings(ohlcv, lookbacks, min_confirmations)` — 多 lookback 共识摆动 — 只在 ≥min_confirmations 个 lookback 都检测到的才是真正结构点。
- `detect_swings_v17(ohlcv, left, right, atr_filter, min_amp_atr)` — Pine语义:
- `_merge_consecutive(swings, ohlcv, is_high)` — 合并3根K线内的同向摆动，取更极值
- `_filter_tiny(swings, min_amp, ohlcv, is_high)` — 过滤幅度过小的连续摆动（基于前一个摆动的幅度）
- `_calc_fvg_strength(gap_size, atr_val)` — Pine SMC 2026: calculate_fvg_strength
- `detect_fvg_v17(ohlcv, adaptive, tf, min_strength, fvg_atr_mult)` — 
- `_check_trend(ohlcv, idx, direction, lookback)` — 
- `_calc_ob_strength(displacement, zone_height, atr_val)` — Pine SMC 2026 strength rating — simplified (no session/age scoring)
- `detect_ob_v17(ohlcv, swings, displacement_mult, ob_swing_length, ob_lookback, adaptive)` — SMC OB detection — finds the LAST opposite candle before a swing.
- `detect_structure_v17(ohlcv, swings, tf, swing_length, structure_spacing)` — Simplified structure detection for zigzag swings.
- `detect_mss_v17(ohlcv, swings, tf, min_spacing, min_break_pct)` — 
- `detect_sweep_v17(ohlcv, swings, tf)` — ICT liquidity sweep:
- `detect_eql_v17(ohlcv, swings, tolerance_pct, atr_val, tf)` — Pine SMC 2026 EQH/EQL exact:
- `detect_bpr_v17(ohlcv, fvg_signals, ob_signals, tf)` — 
- `detect_ifvg_v17(ohlcv, adaptive, tf)` — 
- `detect_all_signals_v17(ohlcv, params, adaptive, tf)` — 
- `to_dict(self)` — 
- `_calc_atr(length)` — 

## hermes\scripts\v11\signals_v18.py
- 类: Signal
- `calc_atr(ohlcv, length)` — 
- `calc_adaptive_thresholds(ohlcv)` — 
- `detect_pivot_swings(ohlcv, left)` — Pine equivalent: ta.pivothigh(high, left, left), ta.pivotlow(low, left, left)
- `detect_ob_v18(ohlcv, ob_swing_length, ob_lookback, ob_displacement_mult, min_strength, adaptive)` — Pine SMC 2026 OB detection:
- `detect_structure_v18(ohlcv, swing_length, min_spacing, show_bos, show_choch)` — Pine SMC 2026 structure detection:
- `detect_fvg_v18(ohlcv, fvg_atr_mult, min_strength, adaptive)` — Pine SMC 2026 FVG detection:
- `detect_sweep_v18(ohlcv, adaptive, min_penetration_pct)` — ICT Sweep: price pierces a prior swing point (high or low), then closes back inside.
- `detect_mss_v18(ohlcv, min_spacing)` — Pine SMC 2026 MSS: close crosses above prior pivot high (or below prior pivot low).
- `detect_eql_v18(ohlcv, adaptive)` — Pine SMC 2026 EQH/EQL: compare only ADJACENT pivot points.
- `detect_bpr_v18(fvg_signals, ob_signals)` — BPR = Balanced Price Range = bull zone AND bear zone overlap.
- `detect_all_signals_v18(ohlcv, params)` — Main entry point for V18 signal detection.
- `to_dict(self)` — 

## hermes\scripts\v11\signals_v19.py
- 类: Signal, SwingPoint
- `_calc_atr(ohlcv, length)` — 
- `detect_leg_swings(ohlcv, leg_size)` — LuxAlgo leg(): high[leg_size] > ta.highest(leg_size) → new bearish leg (swing high)
- `detect_choch_bos_v19(ohlcv, swings, trend_bias)` — LuxAlgo displayStructure():
- `detect_ob_luxalgo(ohlcv, swings, choch_bos_signals)` — LuxAlgo storeOrdeBlock():
- `detect_ob_smc2026(ohlcv, swings)` — SMC 2026 OB: from swing, scan backward for first opposite candle with displacement.
- `detect_fvg_v19(ohlcv, atr_mult, min_strength)` — 
- `detect_sweep_v19(ohlcv, swings)` — Sweep: bar pierces a prior swing point then closes back inside.
- `detect_mss_v19(ohlcv, swings)` — LuxAlgo internal structure: smaller leg size crossover events.
- `detect_eql_v19(ohlcv, swings, atr_val, avg_price)` — LuxAlgo style + A-share percentage adaptation: compare adjacent pivots with 0.5% price tol
- `detect_bpr_v19(fvg_signals, ob_signals)` — 
- `detect_all_signals_v19(ohlcv, params)` — 
- `detect_signal_sequences(signals)` — Find SMC signal sequences in chronological order.
- `to_dict(self)` — 

## hermes\scripts\v11\signals_v20.py
- 类: Signal, SwingPoint
- `_calc_atr(ohlcv, length)` — 
- `detect_leg_swings(ohlcv, leg_size)` — LuxAlgo leg(): high[leg_size] > ta.highest(leg_size) → new bearish leg (swing high)
- `detect_choch_bos_v20(ohlcv, swings)` — V20.1 CHOCH/BOS — 基于摆动点标签判断结构变化.
- `detect_ob_luxalgo(ohlcv, swings, choch_bos_signals)` — LuxAlgo storeOrdeBlock():
- `detect_ob_smc2026(ohlcv, swings)` — SMC 2026 OB: from swing, scan backward for first opposite candle with displacement.
- `detect_fvg_v19(ohlcv, atr_mult, min_strength)` — 
- `detect_sweep_v20(ohlcv, swings)` — V20 Sweep: 放宽穿刺阈值, 扩大摆动点窗口到60根, 增加独立穿刺计数.
- `detect_mss_v20(ohlcv, swings)` — V20 MSS: cooldown 5 bars (was 12), wider window 50 bars (was 40).
- `detect_eql_v20(ohlcv, swings, atr_val, avg_price)` — V20 EQL/EQH: 比较所有同类型pivot(非仅相邻), ATR自适应阈值.
- `detect_bpr_v19(fvg_signals, ob_signals)` — 
- `detect_pinbars_v20(ohlcv)` — SMC Pinbar: entry confirmation at PD Arrays (OB/FVG), NOT standalone signal.
- `detect_all_signals_v20(ohlcv, params)` — V20: 全面修复版信号引擎.
- `_build_sequences(atr_pct)` — Build adapted sequence patterns based on ATR%.
- `detect_signal_sequences(signals, atr_pct)` — Find SMC signal sequences in chronological order.
- `detect_smc_setups(signals, ohlcv)` — V20.2: 完整SMC入场Setup检测 — 时间顺序的流动性→结构→POI流程.
- `to_dict(self)` — 

## hermes\scripts\v11\signals_v21.py
- 类: Signal, SwingPoint
- `_calc_atr(ohlcv, length)` — 
- `detect_leg_swings(ohlcv, leg_size)` — LuxAlgo leg(): high[leg_size] > ta.highest(leg_size) → swing high confirmed
- `detect_choch_bos_v21(ohlcv, swings, atr_val)` — V21: 要求close穿透摆动点ATR*0.3 + 同区域去重
- `detect_ob_luxalgo(ohlcv, swings, choch_bos_signals)` — LuxAlgo OB: at CHOCH/BOS moment, find OB between pivot and break bar
- `detect_ob_smc2026(ohlcv, swings)` — SMC 2026 OB: 从摆动点回看最近的reverse candle
- `detect_fvg_v21(ohlcv, atr_mult, min_strength)` — FVG: 3-candle gap — b2.l > b0.h (bull) or b2.h < b0.l (bear)
- `detect_sweep_v21(ohlcv, swings, atr_val)` — V21: 3-bar cooldown + 最近25bar摆动点 + ATR*0.08穿刺
- `detect_mss_v21(ohlcv, swings, atr_val)` — V21: ATR*0.5穿透 + 8-bar cooldown
- `detect_eql_v21(ohlcv, swings, atr_val, avg_price)` — V21: 修复类型名为EQL_High/EQL_Low, 至少5bar间距, 每pivot最近匹配
- `detect_bpr_v21(fvg_signals, ob_signals)` — 
- `detect_pinbars_v21(ohlcv)` — 
- `detect_smc_setups(signals, ohlcv)` — 
- `detect_all_signals_v21(ohlcv, params)` — 
- `to_dict(self)` — 

## hermes\scripts\v11\signals_v22.py
- 类: Signal, SwingPoint
- `_calc_atr(ohlcv, length)` — 
- `detect_leg_swings(ohlcv, leg_size)` — 
- `detect_choch_bos(ohlcv, swings, atr_val)` — 
- `detect_ob_luxalgo(ohlcv, swings, choch_bos)` — 
- `detect_ob_smc2026(ohlcv, swings)` — 
- `detect_fvg(ohlcv, atr_mult, min_strength)` — 
- `detect_ifvg(ohlcv, fvg_signals)` — IFVG: FVG zone gets filled by price, then acts as opposite zone
- `detect_sweep(ohlcv, swings, atr_val)` — 
- `detect_mss(ohlcv, swings, atr_val)` — 
- `detect_eql(ohlcv, swings, atr_val, avg_price)` — 
- `detect_bpr(fvg_signals, ob_signals)` — 
- `detect_breaker(ohlcv, ob_signals)` — Breaker Block: OB被突破后变成反向支撑/阻力
- `detect_liquidity_void(ohlcv, atr_val)` — LV: 连续K线之间价格跳空，没有交易发生的区域
- `detect_rejection(ohlcv, swings, atr_val)` — RB: 价格快速接近摆动点后强烈反转
- `detect_ote(ohlcv, swings, atr_val)` — OTE: 最近摆动leg的61.8%-79%回撤区域
- `detect_po3(ohlcv, atr_val)` — PO3: 日内/区间 Accumulation→Manipulation→Distribution 模式
- `detect_pinbars(ohlcv)` — 
- `detect_smc_setups(signals, ohlcv)` — 
- `detect_all_signals_v22(ohlcv, params)` — 
- `to_dict(self)` — 

## hermes\scripts\v11\signals_vPine.py
- 类: Signal
- `calc_adaptive_thresholds(ohlcv)` — 自适应阈值计算 — 基于每只股票的波动特性
- `detect_swings_vPine(ohlcv, left, right, min_swing_pct, adaptive, vol_invert)` — Pine-equivalent swing point detection.
- `detect_swings_internal(ohlcv, left, right, min_swing_pct)` — Internal (micro) swing detection — for LuxAlgo-style dual structure.
- `_classify_fvg_width(gap_pct, ohlcv, idx, adaptive)` — FVG宽度分级 1-4
- `_check_trend_alignment(ohlcv, idx, direction)` — 检查信号方向是否与局部趋势对齐
- `_calc_fvg_strength(sig, c2, adaptive)` — FVG强度 (0-10)
- `_calc_fvg_confidence(sig, b1, b2, b3, gap_pct)` — FVG置信度 (0-1)
- `_merge_fvgs_vPine(signals, merge_dist)` — 合并相邻FVG — 去除冗余
- `detect_fvg_vPine(ohlcv, min_width, merge_dist, adaptive, tf)` — Enhanced FVG detection — keeps existing V11 quality with Pine refinements.
- `_classify_wick(ratio)` — 
- `_calc_sweep_strength_vPine(cur, wick, wick_ratio, wick_grade, adaptive, at_swing)` — 
- `_calc_sweep_confidence_vPine(cur, wick_ratio, vol_ok, at_swing)` — 
- `detect_sweep_vPine(ohlcv, lookback, wick_ratio, adaptive, require_volume, require_reversal)` — Sweep detection — uses Pine-quality swings if provided.
- `_is_near_swing_vPine(idx, swing_idxs, max_dist)` — 
- `_calc_ob_strength_vPine(body_pct, volume, vol_median, adaptive, displacement_ratio)` — OB strength (0-10) — Pine-quality rating.
- `_calc_ob_confidence_vPine(body_pct, vol_ok, at_structure, impulse_bars, displacement_ratio)` — OB confidence (0-1) — Pine quality
- `detect_ob_vPine(ohlcv, strength_min, adaptive, require_volume, displacement_mult, swings)` — Pine-quality Order Block detection — 🎯 KEY IMPROVEMENT.
- `detect_structure_vPine(ohlcv, swings, tf)` — State machine structure detection — replaces rigid sequence matching.
- `detect_eql_vPine(ohlcv, pivot_length, threshold_pct, swings, tf)` — Pivot-based EQH/EQL detection — UAlgo style.
- `_find_swing_highs_vPine(ohlcv, lookback)` — Quick swing high detection (no right confirmation, for sweep detection).
- `_find_swing_lows_vPine(ohlcv, lookback)` — 
- `detect_bpr_vPine(ohlcv, fvg_signals, tf)` — BPR — same as V11
- `detect_liquidity_void_vPine(ohlcv, min_gap_pct, tf)` — Liquidity Void — same as V11
- `detect_rejection_block_vPine(ohlcv, min_wick_pct, min_reversal, tf)` — Rejection Block — same as V11
- `detect_ifvg_vPine(ohlcv, min_width, adaptive, tf)` — IFVG — same as V11
- `detect_mitigated_fvg_vPine(ohlcv, fvg_signals, tf)` — Mitigated FVG — same as V11
- `detect_breaker_block_vPine(ohlcv, choch_signals, ob_signals, fvg_signals, tf)` — Breaker Block — same as V11
- `detect_ote_vPine(ohlcv, tf)` — OTE — same as V11
- `detect_mss_vPine(ohlcv, lookback, min_confirm, tf)` — MSS — same as V11
- `detect_po3_vPine(ohlcv, lookback, adaptive, tf)` — PO3 — same as V11
- `detect_all_signals_vPine(ohlcv, params, adaptive, tf)` — V-Pine统一信号检测入口 — 完全兼容V11接口。
- `to_dict(self)` — 
- `_near_swing(idx, price, is_high, window)` — 
- `_is_strong_impulse(start, direction, min_bars)` — 

## hermes\scripts\v11\smc_sequence_engine.py
- `detect_sequences(signals, active_patterns)` — 检测所有匹配的SMC序列。返回 [{pattern, signals, entry_bar, direction, ...}].
- `backtest_sequences(ohlcv, sequences, signals, swings_dict)` — 执行序列入场交易.
- `compute_stats(trades, label)` — 计算策略统计.

## hermes\scripts\v11\smc_setup_backtest.py
- `calc(stat, name)` — 

## hermes\scripts\v11\split_adjuster.py
- `detect_splits(ohlcv, threshold)` — 检测拆股/送转股事件。
- `adjust_forward(ohlcv, splits)` — 前向复权: 将split_bar之前所有bar的价格乘以 1/forward_mult。
- `load_adjusted(symbol, cache_dir)` — 加载并前复权K线数据。
- `scan_all_splits(cache_dir, limit)` — 扫描所有股票的拆股/送转股事件

## hermes\scripts\v11\stock_dna_v11.py
- `calc_sl(zone_type, zone_low, entry_price)` — V11 optimized: tighter SL for FVG, standard for OB
- `daily_to_weekly(d)` — 
- `weekly_trend(w)` — 
- `detect_sequences(signals)` — 
- `backtest(ohlcv, seqs, use_v11_sl)` — V8 or V11 SL depending on flag

## hermes\scripts\v11\stock_screener_v23.py
- `load_ohlcv(symbol)` — 
- `assess_swing_quality(ohlcv, symbol)` — Score a stock's swing structure quality (0-100)
- `main()` — 

## hermes\scripts\v11\stock_signal_matrix.py

## hermes\scripts\v11\strategy_v72.py
- `weekly_trend(daily)` — 
- `load_ohlcv(symbol)` — 
- `execute_strategy_trade(daily, pick, signal_cache)` — Execute trade with honest strategy rules. Returns trade dict or None.

## hermes\scripts\v11\structural_swings.py
- `classify_swings(swing_highs, swing_lows)` — 给每个摆动点标注结构类型: HH, LH, HL, LL, or None
- `filter_structural_swings(swings_dict)` — 从原始摆动中过滤出结构性摆动(HH/HL/LL/LH)
- `filter_by_min_amplitude(swings_dict, min_pct)` — 额外过滤: 与前一个同向摆动幅度不足 min_pct% 的摆动

## hermes\scripts\v11\structure_sl_tp.py
- `find_recent_swing_low(ohlcv, entry_idx, lookback)` — 找最近的摆动低点(结构SL候选)
- `find_recent_swing_high(ohlcv, entry_idx, lookback)` — 找最近的摆动高点(TP候选)
- `find_next_swing_high(ohlcv, entry_idx, lookahead)` — 找入场后的下一个摆动高点(TP目标)
- `find_fvg_lower(ohlcv, entry_idx, all_signals, lookback)` — 找最近的FVG下边界作为SL基础
- `find_ob_bottom(ohlcv, entry_idx, all_signals, lookback)` — 找最近的OB下边界
- `find_sweep_low(ohlcv, entry_idx, all_signals, lookback)` — 找最近的扫荡低点(SweepDown的low)
- `calc_structure_sl(ohlcv, entry_price, entry_idx, all_signals, atr_pct)` — SMC结构感知止损计算
- `calc_structure_tp(ohlcv, entry_price, entry_idx, sl_price, all_signals, atr_pct)` — SMC结构感知止盈计算
- `calc_structure_sl_tp(ohlcv, entry_price, entry_idx, all_signals)` — 完整SMC结构SL/TP计算
- `calc_trailing_structure(ohlcv, entry_idx, entry_price, initial_sl, all_signals, max_hold)` — SMC结构感知追踪止损

## hermes\scripts\v11\structure_tree_v38.py
- 类: StructureTree
- `detect_swings(ohlcv, window, min_bars)` — 检测所有摆动高点和低点
- `calc_atr_v38(ohlcv, idx, period)` — 
- `calc_stock_atr_profile(ohlcv)` — 计算股票的ATR特征 — 用于参数自适应
- `_calc_trend(self, highs, lows, lookback)` — 基于最近的HH/HL序列判断趋势
- `_calc_levels(self, highs, lows)` — 关键价格水平: 前摆动高点和低点
- `get_sl_level(self, entry_idx, entry_price)` — 基于结构树的止损水平
- `get_tp_level(self, entry_idx, entry_price, direction)` — 基于结构树的止盈水平
- `get_multi_level_support(self)` — 获取多层支撑 — 用于阶段判断
- `get_multi_level_resistance(self)` — 获取多层阻力
- `is_consolidation(self, lookback)` — 检测是否在盘整 (价格被压缩在窄区间)
- `summary(self, at_idx)` — 在指定位置的结构摘要

## hermes\scripts\v11\structure_zones_v17.py
- `scan_structure_zones(ohlcv, signals_v17, entry_bar, entry_price, direction)` — 扫描入场点前后的所有结构区域。
- `_add_zone(zones, typ, bar, price, entry_price, strength)` — 添加结构区域，自动计算距离
- `_scan_bull_tp(ohlcv, signals, entry_bar, entry_price, tp_zones, min_tp_pct)` — 扫描做多TP目标 (入场价上方)
- `_scan_bull_sl(ohlcv, signals, entry_bar, entry_price, sl_zones, min_sl_pct)` — 扫描做多SL支撑 (入场价下方)
- `_scan_bear_tp(ohlcv, signals, entry_bar, entry_price, tp_zones, min_tp_pct)` — 扫描做空TP目标 (入场价下方)
- `_scan_bear_sl(ohlcv, signals, entry_bar, entry_price, sl_zones, min_sl_pct)` — 扫描做空SL阻力 (入场价上方)
- `_dedup_zones(zones, atr_val, price_tolerance_pct)` — 合并价格过于接近的区域（同一结构的不同表现形式）
- `_score_entry_quality(tp_zones, sl_zones, entry_bar, signals, atr_val)` — 入场质量评分 (0-10)

## hermes\scripts\v11\test_diagnose.py

## hermes\scripts\v11\test_imports.py

## hermes\scripts\v11\test_ob_disp.py

## hermes\scripts\v11\test_poi_diagnostic.py
- `deep_diagnose(symbol, ohlcv)` — 

## hermes\scripts\v11\test_v12_20.py

## hermes\scripts\v11\test_v12_backtest.py
- `load_kline(code)` — 
- `backtest_stock(ohlcv, code, adaptive)` — V12 signals + V467 trailing = clean exit with correct signal entry.
- `main()` — 

## hermes\scripts\v11\test_v12_diag.py

## hermes\scripts\v11\test_v12_mult.py

## hermes\scripts\v11\test_v12_quick.py

## hermes\scripts\v11\test_v12_signals.py
- `load_kline(code)` — Load kline from cache.

## hermes\scripts\v11\test_v12_verify.py

## hermes\scripts\v11\test_v44_import.py

## hermes\scripts\v11\test_v470_200.py

## hermes\scripts\v11\test_v470_full.py

## hermes\scripts\v11\test_v470_funnel.py
- `diagnose_stock(symbol, ohlcv)` — 

## hermes\scripts\v11\test_vPine_signals.py
- `load_ohlcv(symbol)` — 

## hermes\scripts\v11\tf_data.py
- `_normalize_klines(raw_data, symbol, interval)` — 标准化K线数据到统一格式
- `_cache_path(symbol, interval, bars)` — 
- `_read_cache(symbol, interval, bars, max_age_hours)` — 
- `_write_cache(symbol, interval, bars, data)` — 
- `fetch_single_tf(symbol, interval, bars, limiter, skip_cache)` — 获取单个TF的K线数据
- `fetch_multi_tf(symbol, tfs, limiter)` — 并行获取多个TF的K线数据
- `get_a_stock_symbols(limit)` — 获取A股股票代码列表
- `get_etf_symbols()` — 获取ETF代码列表
- `get_index_symbols()` — 获取指数代码列表
- `get_sector_symbols()` — 获取板块指数列表 (申万一级)
- `get_universe()` — 获取全量测试 universe
- `calc_atr(ohlcv, period)` — 计算ATR
- `calc_atr_pct(ohlcv, period)` — 计算ATR百分比
- `test_fetch(symbol)` — 快速测试多周期获取
- `fetch_one(tf)` — 
- `worker(tf)` — 

## hermes\scripts\v11\today_refresh_pick.py
- `refresh_one(sym)` — Download daily from Tencent

## hermes\scripts\v11\trading_system_v3.py
- `detect_sequences(signals)` — 
- `backtest(ohlcv, sequences, weekly_trend, signals, swings_dict)` — 交易回测: T+1, TP/SL结构止盈, 周线趋势过滤.

## hermes\scripts\v11\v10_smart_money_engine.py
- `_calc_atr(closes, highs, lows, length)` — 
- `_has_pinbar_at_zone(daily, zone_low, zone_high, entry_bar)` — Check for Pinbar confirmation at entry zone
- `_find_swing_low(daily, entry_idx)` — 找entry前最近的摆动低点作为结构性SL参考
- `_check_fvg_fill_rate(daily, fvg_sig)` — 检查FVG回补率
- `check_signal_context(sig, all_sigs, symbol)` — V10: 检查信号是否有SMC上下文确认
- `get_adaptive_sl(daily, entry_idx, entry_price, signal)` — V10: 自适应SL — 结构性SL + ATR自适应
- `simulate_smart_trailing(daily, entry_idx, entry_price, sl, tp_price)` — V10: Smart Trailing — 延迟激活 + 回测zone后收紧
- `backtest_stock_v10(symbol, daily, weekly, hourly)` — V10单股票回测
- `run_backtest(limit)` — 

## hermes\scripts\v11\v11_complete_engine.py
- `detect_market_state(daily, weekly)` — 识别市场状态: trending_up / ranging / trending_down / volatile
- `get_adaptive_params(state, state_info)` — 根据市场状态返回自适应参数
- `detect_breaker_blocks(daily, signals)` — Breaker: 失败的OB → 价格穿越OB后变为反向支撑/阻力
- `detect_mitigation_blocks(daily, signals)` — Mitigation: FVG被回补后变成支撑/阻力
- `detect_rejection_blocks(daily)` — Rejection: 价格测试某个水平后强势反转
- `detect_turtle_soup(daily, signals)` — Turtle Soup: 假突破前期高/低点后反转
- `check_resonance(daily, weekly, hourly, sig)` — 检查信号在多个时间周期上是否共振
- `calc_dynamic_sltp(daily, entry_idx, entry_price, sig, params)` — 动态SL/TP: 聪明钱成本线 + 分批止盈
- `simulate_batch_exit(daily, entry_idx, entry_price, sltp)` — 分批止盈模拟: 50%@TP1 + 30%@TP2 + 20%@Trailing
- `backtest_stock_v11(symbol, daily, weekly, hourly)` — 
- `run_full_backtest(limit)` — 

## hermes\scripts\v11\v12_engine.py
- `calc_atr(daily, length)` — 
- `detect_market_state(daily)` — 
- `calc_sltp(daily, entry_idx, entry_price, cost_line, state)` — 
- `simulate_exit(daily, entry_idx, entry_price, sltp)` — 
- `backtest_stock_v12(symbol, daily, weekly)` — 
- `run_full_backtest(limit, start_idx)` — 

## hermes\scripts\v11\v13_engine.py
- `calc_atr(daily, length)` — 
- `calc_sltp(daily, entry_idx, entry_price, cost_line)` — 
- `simulate_exit(daily, entry_idx, entry_price, sltp)` — 
- `classify_zone(zone_bar, zone_low, zone_high, daily, sigs, atr)` — 分类Zone有效性: 未击穿 / PO3反转(击穿后CHOCH) / 击穿无效
- `backtest_stock_v13(symbol, daily)` — 
- `run_full(limit)` — 

## hermes\scripts\v11\v13_fast_scan.py
- `calc_atr(daily, L)` — 
- `sim_exit(daily, eidx, ep, sl_price)` — 

## hermes\scripts\v11\v13_scan.py
- `calc_atr(daily, L)` — 
- `calc_sltp(daily, eidx, ep, cl)` — 
- `sim_exit(daily, eidx, ep, sltp)` — 
- `scan_params(daily_files, age_limits, require_choch)` — 扫描不同zone年龄限制+CHOCH要求的回测结果

## hermes\scripts\v11\v14_fast.py
- `calc_atr(daily, L)` — 
- `sim_exit(daily, eidx, ep, sl_price, tp_price, max_bars)` — 

## hermes\scripts\v11\v14_scan.py
- `calc_atr(daily, L)` — 
- `sim_exit(daily, eidx, ep, sl_price, tp_price, max_bars)` — V14增强退出: 支持结构TP目标

## hermes\scripts\v11\v16_dashboard.py
- 类: Handler
- `generate_html()` — 
- `do_GET(self)` — 
- `send_json(self, data)` — 
- `_load_ohlcv(self, symbol)` — 

## hermes\scripts\v11\v17_backtest_engine.py
- `backtest_stock_v17(ohlcv, min_quality, direction)` — 单只股票V17完整回测。
- `_simulate_trailing_exit(ohlcv, entry_bar, entry_price, sl_price, tp_price)` — 带简单trailing的退出模拟。
- `run_backtest(stock_files, min_quality, verbose)` — 多股票V17回测。

## hermes\scripts\v11\v18_backtest_engine.py
- 类: Trade
- `find_structural_tp(ohlcv, entry_idx, entry_price, signals, swings)` — Find CLOSEST structural TP above entry price.
- `find_structural_sl(ohlcv, entry_idx, entry_price, signals, swings)` — Find CLOSEST structural SL below entry price.
- `_calc_atr(ohlcv, length)` — 
- `trailing_exit(ohlcv, entry_idx, entry_price, sl_price, tp_price)` — Progressive BE lock trailing stop.
- `backtest_stock_v18(symbol, ohlcv, signals, swings, params)` — Backtest a single stock with V18 engine.
- `backtest_v18(symbol, signals_func)` — Full V18 backtest: load data -> detect signals -> backtest.
- `to_dict(self)` — 

## hermes\scripts\v11\v19_backtest_engine.py
- 类: TradeV19
- `_atr(ohlcv, length)` — 
- `find_tps(entry_price, signals, swings_dict, ohlcv)` — Multi-source TP: scan ALL resistance points ABOVE entry
- `find_sls(entry_price, signals, swings_dict, ohlcv)` — Multi-source SL: scan ALL support points BELOW entry
- `backtest_v19(symbol, ohlcv, all_signals, swings_dict, sequences)` — V19 backtest with T+1 enforcement + multi-source TP/SL.
- `to_dict(self)` — 

## hermes\scripts\v11\v20_backtest.py

## hermes\scripts\v11\v20_comparison.py

## hermes\scripts\v11\v392_per_stock_opt.py
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_v38_sl(ohlcv, entry_idx, entry_price, signal, entry_type, structure_tree)` — V38结构SL计算 (3层优先级)
- `calc_v38_trailing(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V38.4 差异化trailing (与原始版本完全一致)
- `evaluate_v38_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n, structure_tree)` — V38统一入场评估 (支持custom_sl_mult)
- `calc_v38_tp(ohlcv, entry_idx, entry_price, signal, entry_type, structure_tree)` — V38结构TP计算 (与原始版本完全一致)
- `backtest_stock_v38(ohlcv, symbol, custom_sl_mult)` — 单股票V38回测 (支持custom_sl_mult)
- `main()` — 

## hermes\scripts\v11\v44_backtest_test.py

## hermes\scripts\v11\v44_backtest_test_a.py

## hermes\scripts\v11\v44_backtest_test_b.py

## hermes\scripts\v11\v44_engine.py
- 类: RetestEntry
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_atr(ohlcv, idx, period)` — 
- `find_best_swing_sl(ohlcv, entry_idx, entry_price, direction, lookback)` — 找最佳摆动点止损
- `detect_market_phase(ohlcv, lookback)` — 检测市场阶段
- `synthesize_weekly(ohlcv_daily)` — 日线合成周线
- `weekly_trend(weekly, lookback)` — 周线趋势
- `calc_stock_params(ohlcv, symbol, phase, tf)` — 计算股票自适应参数
- `detect_ob_v14(ohlcv, adaptive, require_volume, require_trend_context, require_swing_proximity, min_impulse_bars)` — V14 OB — 重构版 (减少误报)
- `detect_retest_entries(ohlcv, signals, params, tf)` — 回踩入场检测 — V44核心
- `_detect_retest_confirmation(ohlcv, idx, zone)` — 检测回踩确认形态
- `_calc_retest_quality(zone, bar, retest_type, ohlcv, idx, params)` — 回踩质量评分 (0-1)
- `_calc_bar_zone_pct(bar, zone)` — 计算K线在信号区间中的位置比例
- `_calc_volume_at_retest(ohlcv, idx, lookback)` — 回踩时的相对成交量
- `find_swing_highs(ohlcv, lookback)` — 
- `find_swing_lows(ohlcv, lookback)` — 
- `find_swing_high_forward(ohlcv, entry_idx, lookahead)` — 
- `calc_structural_sl_v44(ohlcv, entry_idx, entry_price, signal, direction, params)` — V44结构止损: 3层优先级
- `calc_structural_tp_v44(ohlcv, entry_idx, entry_price, direction, all_signals)` — V44结构止盈: 多层TP目标
- `find_swing_low_forward(ohlcv, entry_idx, lookahead)` — 
- `calc_trailing_v44(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V44动态Trailing — 质量等级差异化 + V38.4风格
- `get_quality_grade(resonance_total, seq_name, has_retest)` — 确定信号质量等级
- `evaluate_signal_entry_v44(ohlcv, sig_idx, sig, all_sigs_up_to_idx, all_signals, params)` — V44统一入场评估 (支持回踩 + 多入口 + 做空 + 质量分级)
- `_evaluate_retest_entry(ohlcv, retest, all_signals, params, phase)` — 评估回踩入场
- `backtest_stock_v44(ohlcv, symbol)` — 
- `main()` — 
- `_is_near_swing_strict(idx, max_dist)` — 更严格的摆动点接近检测
- `_is_at_swing_high(idx, max_dist)` — 
- `_is_at_swing_low(idx, max_dist)` — 
- `_is_strong_impulse_v14(start, direction, min_bars)` — 更强力的impulse检测: 要求3+根同向K线且覆盖OB实体
- `_verify_ob_breakout(ob_idx, direction, ob_price)` — 验证OB后的价格是否有效突破OB极值 (减少假信号)
- `_calc_ob_quality_score(bar, impulse_bars, at_swing, vol_ok, body_pct, atr)` — OB质量评分 (0-1): V14更严格

## hermes\scripts\v11\v44_engine_a.py
- 类: RetestEntry
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_atr(ohlcv, idx, period)` — 
- `find_best_swing_sl(ohlcv, entry_idx, entry_price, direction, lookback)` — 找最佳摆动点止损
- `detect_market_phase(ohlcv, lookback)` — 检测市场阶段
- `synthesize_weekly(ohlcv_daily)` — 日线合成周线
- `weekly_trend(weekly, lookback)` — 周线趋势
- `calc_stock_params(ohlcv, symbol, phase, tf)` — 计算股票自适应参数
- `detect_ob_v14(ohlcv, adaptive, require_volume, require_trend_context, require_swing_proximity, min_impulse_bars)` — V14 OB — 重构版 (减少误报)
- `detect_retest_entries(ohlcv, signals, params, tf)` — 回踩入场检测 — V44核心
- `_detect_retest_confirmation(ohlcv, idx, zone)` — 检测回踩确认形态
- `_calc_retest_quality(zone, bar, retest_type, ohlcv, idx, params)` — 回踩质量评分 (0-1)
- `_calc_bar_zone_pct(bar, zone)` — 计算K线在信号区间中的位置比例
- `_calc_volume_at_retest(ohlcv, idx, lookback)` — 回踩时的相对成交量
- `find_swing_highs(ohlcv, lookback)` — 
- `find_swing_lows(ohlcv, lookback)` — 
- `find_swing_high_forward(ohlcv, entry_idx, lookahead)` — 
- `calc_structural_sl_v44(ohlcv, entry_idx, entry_price, signal, direction, params)` — V44结构止损: 3层优先级
- `calc_structural_tp_v44(ohlcv, entry_idx, entry_price, direction, all_signals)` — V44结构止盈: 多层TP目标
- `find_swing_low_forward(ohlcv, entry_idx, lookahead)` — 
- `find_swing_high_forward_skip(ohlcv, entry_idx, lookahead)` — 
- `find_swing_low_forward_skip(ohlcv, entry_idx, lookahead)` — 
- `calc_trailing_v44(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V44动态Trailing — 质量等级差异化 + V38.4风格
- `get_quality_grade(resonance_total, seq_name, has_retest)` — 确定信号质量等级
- `evaluate_signal_entry_v44(ohlcv, sig_idx, sig, all_sigs_up_to_idx, all_signals, params)` — V44统一入场评估 (支持回踩 + 多入口 + 做空 + 质量分级)
- `_evaluate_retest_entry(ohlcv, retest, all_signals, params, phase)` — 评估回踩入场
- `backtest_stock_v44(ohlcv, symbol)` — 
- `main()` — 
- `_is_near_swing_strict(idx, max_dist)` — 更严格的摆动点接近检测
- `_is_at_swing_high(idx, max_dist)` — 
- `_is_at_swing_low(idx, max_dist)` — 
- `_is_strong_impulse_v14(start, direction, min_bars)` — 更强力的impulse检测: 要求3+根同向K线且覆盖OB实体
- `_verify_ob_breakout(ob_idx, direction, ob_price)` — 验证OB后的价格是否有效突破OB极值 (减少假信号)
- `_calc_ob_quality_score(bar, impulse_bars, at_swing, vol_ok, body_pct, atr)` — OB质量评分 (0-1): V14更严格

## hermes\scripts\v11\v44_engine_b.py
- 类: RetestEntry
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_atr(ohlcv, idx, period)` — 
- `find_best_swing_sl(ohlcv, entry_idx, entry_price, direction, lookback)` — 找最佳摆动点止损
- `detect_market_phase(ohlcv, lookback)` — 检测市场阶段
- `synthesize_weekly(ohlcv_daily)` — 日线合成周线
- `weekly_trend(weekly, lookback)` — 周线趋势
- `calc_stock_params(ohlcv, symbol, phase, tf)` — 计算股票自适应参数
- `detect_ob_v14(ohlcv, adaptive, require_volume, require_trend_context, require_swing_proximity, min_impulse_bars)` — V14 OB — 重构版 (减少误报)
- `detect_retest_entries(ohlcv, signals, params, tf)` — 回踩入场检测 — V44核心
- `_detect_retest_confirmation(ohlcv, idx, zone)` — 检测回踩确认形态
- `_calc_retest_quality(zone, bar, retest_type, ohlcv, idx, params)` — 回踩质量评分 (0-1)
- `_calc_bar_zone_pct(bar, zone)` — 计算K线在信号区间中的位置比例
- `_calc_volume_at_retest(ohlcv, idx, lookback)` — 回踩时的相对成交量
- `find_swing_highs(ohlcv, lookback)` — 
- `find_swing_lows(ohlcv, lookback)` — 
- `find_swing_high_forward(ohlcv, entry_idx, lookahead)` — 
- `calc_structural_sl_v44(ohlcv, entry_idx, entry_price, signal, direction, params)` — V44结构止损: 3层优先级
- `calc_structural_tp_v44(ohlcv, entry_idx, entry_price, direction, all_signals)` — V44结构止盈: 多层TP目标
- `find_swing_low_forward(ohlcv, entry_idx, lookahead)` — 
- `calc_trailing_v44(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V44动态Trailing — 质量等级差异化 + V38.4风格
- `get_quality_grade(resonance_total, seq_name, has_retest)` — 确定信号质量等级
- `evaluate_signal_entry_v44(ohlcv, sig_idx, sig, all_sigs_up_to_idx, all_signals, params)` — V44统一入场评估 (支持回踩 + 多入口 + 做空 + 质量分级)
- `_evaluate_retest_entry(ohlcv, retest, all_signals, params, phase)` — 评估回踩入场
- `backtest_stock_v44(ohlcv, symbol)` — 
- `main()` — 
- `_is_near_swing_strict(idx, max_dist)` — 更严格的摆动点接近检测
- `_is_at_swing_high(idx, max_dist)` — 
- `_is_at_swing_low(idx, max_dist)` — 
- `_is_strong_impulse_v14(start, direction, min_bars)` — 更强力的impulse检测: 要求3+根同向K线且覆盖OB实体
- `_verify_ob_breakout(ob_idx, direction, ob_price)` — 验证OB后的价格是否有效突破OB极值 (减少假信号)
- `_calc_ob_quality_score(bar, impulse_bars, at_swing, vol_ok, body_pct, atr)` — OB质量评分 (0-1): V14更严格

## hermes\scripts\v11\v44_engine_c.py
- 类: RetestEntry
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_atr(ohlcv, idx, period)` — 
- `find_best_swing_sl(ohlcv, entry_idx, entry_price, direction, lookback)` — 找最佳摆动点止损
- `detect_market_phase(ohlcv, lookback)` — 检测市场阶段
- `synthesize_weekly(ohlcv_daily)` — 日线合成周线
- `weekly_trend(weekly, lookback)` — 周线趋势
- `calc_stock_params(ohlcv, symbol, phase, tf)` — 计算股票自适应参数
- `detect_ob_v14(ohlcv, adaptive, require_volume, require_trend_context, require_swing_proximity, min_impulse_bars)` — V14 OB — 重构版 (减少误报)
- `detect_retest_entries(ohlcv, signals, params, tf)` — 回踩入场检测 — V44核心
- `_detect_retest_confirmation(ohlcv, idx, zone)` — 检测回踩确认形态
- `_calc_retest_quality(zone, bar, retest_type, ohlcv, idx, params)` — 回踩质量评分 (0-1)
- `_calc_bar_zone_pct(bar, zone)` — 计算K线在信号区间中的位置比例
- `_calc_volume_at_retest(ohlcv, idx, lookback)` — 回踩时的相对成交量
- `find_swing_highs(ohlcv, lookback)` — 
- `find_swing_lows(ohlcv, lookback)` — 
- `find_swing_high_forward(ohlcv, entry_idx, lookahead)` — 
- `calc_structural_sl_v44(ohlcv, entry_idx, entry_price, signal, direction, params)` — V44结构止损: 3层优先级
- `calc_structural_tp_v44(ohlcv, entry_idx, entry_price, direction, all_signals)` — V44结构止盈: 多层TP目标
- `find_swing_low_forward(ohlcv, entry_idx, lookahead)` — 
- `calc_trailing_v44(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V44动态Trailing — 质量等级差异化 + V38.4风格
- `get_quality_grade(resonance_total, seq_name, has_retest)` — 确定信号质量等级
- `evaluate_signal_entry_v44(ohlcv, sig_idx, sig, all_sigs_up_to_idx, all_signals, params)` — V44统一入场评估 (支持回踩 + 多入口 + 做空 + 质量分级)
- `_evaluate_retest_entry(ohlcv, retest, all_signals, params, phase)` — 评估回踩入场
- `backtest_stock_v44(ohlcv, symbol)` — 
- `main()` — 
- `_is_near_swing_strict(idx, max_dist)` — 更严格的摆动点接近检测
- `_is_at_swing_high(idx, max_dist)` — 
- `_is_at_swing_low(idx, max_dist)` — 
- `_is_strong_impulse_v14(start, direction, min_bars)` — 更强力的impulse检测: 要求3+根同向K线且覆盖OB实体
- `_verify_ob_breakout(ob_idx, direction, ob_price)` — 验证OB后的价格是否有效突破OB极值 (减少假信号)
- `_calc_ob_quality_score(bar, impulse_bars, at_swing, vol_ok, body_pct, atr)` — OB质量评分 (0-1): V14更严格

## hermes\scripts\v11\v44_full_scan.py

## hermes\scripts\v11\v44_smoke.py

## hermes\scripts\v11\v45_200_test.py

## hermes\scripts\v11\v45_combo_test.py

## hermes\scripts\v11\v45_engine.py
- `calc_v38_trailing(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V38.4 差异化trailing + V42 BE/LK参数
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_atr_v45(ohlcv, idx, period)` — 
- `find_swing_highs(ohlcv, lookback)` — 
- `find_swing_lows(ohlcv, lookback)` — 
- `find_swing_high_forward(ohlcv, entry_idx, lookahead)` — 最近的前方摆动高
- `find_swing_low_forward(ohlcv, entry_idx, lookahead)` — 最近的前方摆动低
- `check_poi_activation(ohlcv, sig, entry_bar, direction)` — POI激活: 信号(如FVG/OB)的上下沿区域 = POI.
- `calc_v45_sl(ohlcv, entry_idx, entry_price, signal, entry_type, direction)` — V45 SL: 信号边界 > 摆动点 > ATR自适应
- `calc_v45_tp(ohlcv, entry_idx, entry_price, signal, direction, all_signals)` — V45 TP: 前方CHOCH > 前方摆动 > 无TP
- `_calc_entry_price_at_zone(ohlcv, entry_bar, sig, sig_dir)` — 价格区间入场计算 — 信号是范围(FVG/OB区域), 非单点。
- `evaluate_v45_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n, direction)` — V45统一入场评估 (POI激活 + V38出口)
- `calc_stock_params_v45(ohlcv, symbol)` — 计算每只股票自适应参数 (ATR + BE/LK)
- `backtest_stock_v45(ohlcv, symbol)` — V45单股票回测
- `run_backtest(symbols, label)` — 通用回测运行器

## hermes\scripts\v11\v45_full_scan.py

## hermes\scripts\v11\v45_inspect.py

## hermes\scripts\v11\v45_ob_full.py

## hermes\scripts\v11\v45_ob_test.py

## hermes\scripts\v11\v45_report.py

## hermes\scripts\v11\v45_smoke_test.py

## hermes\scripts\v11\v45_smoke_v2.py

## hermes\scripts\v11\v463_200_test.py

## hermes\scripts\v11\v463_engine.py
- `calc_v38_trailing(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V38.4 差异化trailing + V42 BE/LK参数
- `is_reversal_ob(ohlcv, sig, all_signals)` — 判断OB是否在结构反转处 (延续上升中的pullback不算)
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_atr_v45(ohlcv, idx, period)` — 
- `find_swing_highs(ohlcv, lookback)` — 
- `find_swing_lows(ohlcv, lookback)` — 
- `find_swing_high_forward(ohlcv, entry_idx, lookahead)` — 最近的前方摆动高
- `find_swing_low_forward(ohlcv, entry_idx, lookahead)` — 最近的前方摆动低
- `check_poi_activation(ohlcv, sig, entry_bar, direction)` — POI激活: 信号(如FVG/OB)的上下沿区域 = POI.
- `calc_v45_sl(ohlcv, entry_idx, entry_price, signal, entry_type, direction)` — V45 SL: 信号边界 > 摆动点 > ATR自适应
- `calc_v45_tp(ohlcv, entry_idx, entry_price, signal, direction, all_signals)` — V45 TP: 前方CHOCH > 前方摆动 > 无TP
- `_calc_entry_price_at_zone(ohlcv, entry_bar, sig, sig_dir)` — 价格区间入场计算 — 信号是范围(FVG/OB区域), 非单点。
- `evaluate_v45_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n, direction)` — V45统一入场评估 (POI激活 + V38出口)
- `calc_stock_params_v45(ohlcv, symbol)` — 计算每只股票自适应参数 (ATR + BE/LK)
- `backtest_stock_v45(ohlcv, symbol)` — V45单股票回测
- `run_backtest(symbols, label)` — 通用回测运行器

## hermes\scripts\v11\v463_full_scan.py

## hermes\scripts\v11\v464_200_test.py

## hermes\scripts\v11\v464_engine.py
- `calc_v38_trailing(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V464 多目标trailing: 原始V463紧trailing + TP1到达后松
- `is_reversal_ob(ohlcv, sig, all_signals)` — 判断OB是否在结构反转处 (延续上升中的pullback不算)
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_atr_v45(ohlcv, idx, period)` — 
- `find_swing_highs(ohlcv, lookback)` — 
- `find_swing_lows(ohlcv, lookback)` — 
- `find_swing_high_forward(ohlcv, entry_idx, lookahead)` — 最近的前方摆动高
- `find_swing_low_forward(ohlcv, entry_idx, lookahead)` — 最近的前方摆动低
- `find_macro_swing_high(ohlcv, entry_idx, lookahead, lookback)` — V464: 20-bar宏观摆动高 — 捕获中期结构, 非局部小顶
- `find_macro_swing_low(ohlcv, entry_idx, lookahead, lookback)` — V464: 20-bar宏观摆动低
- `check_poi_activation(ohlcv, sig, entry_bar, direction)` — POI激活: 信号(如FVG/OB)的上下沿区域 = POI.
- `calc_v45_sl(ohlcv, entry_idx, entry_price, signal, entry_type, direction)` — V464 SL: 信号边界 > 摆动点 > ATR自适应 (原始距离, 不紧缩)
- `calc_v45_tp(ohlcv, entry_idx, entry_price, signal, direction, all_signals)` — V464 多级TP: CHOCH > nearest swing > 20-bar swing > fib 1.272 > fib 1.618
- `_calc_entry_price_at_zone(ohlcv, entry_bar, sig, sig_dir)` — 价格区间入场计算 — 信号是范围(FVG/OB区域), 非单点。
- `evaluate_v45_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n, direction)` — V45统一入场评估 (POI激活 + V38出口)
- `calc_stock_params_v45(ohlcv, symbol)` — V464 每只股票自适应参数: ATR + BE/LK + SL紧缩乘数
- `backtest_stock_v45(ohlcv, symbol)` — V45单股票回测
- `run_backtest(symbols, label)` — V464 回测运行器 — SL紧缩×0.5 + Trailing×2宽松 + 多级TP + 宏观摆动

## hermes\scripts\v11\v464_engine_a.py
- `calc_v38_trailing(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V464 多目标trailing: 原始V463紧trailing + TP1到达后松
- `is_reversal_ob(ohlcv, sig, all_signals)` — 判断OB是否在结构反转处 (延续上升中的pullback不算)
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_atr_v45(ohlcv, idx, period)` — 
- `find_swing_highs(ohlcv, lookback)` — 
- `find_swing_lows(ohlcv, lookback)` — 
- `find_swing_high_forward(ohlcv, entry_idx, lookahead)` — 最近的前方摆动高
- `find_swing_low_forward(ohlcv, entry_idx, lookahead)` — 最近的前方摆动低
- `find_macro_swing_high(ohlcv, entry_idx, lookahead, lookback)` — V464: 20-bar宏观摆动高 — 捕获中期结构, 非局部小顶
- `find_macro_swing_low(ohlcv, entry_idx, lookahead, lookback)` — V464: 20-bar宏观摆动低
- `check_poi_activation(ohlcv, sig, entry_bar, direction)` — POI激活: 信号(如FVG/OB)的上下沿区域 = POI.
- `calc_v45_sl(ohlcv, entry_idx, entry_price, signal, entry_type, direction)` — V464 SL: 信号边界 > 摆动点 > ATR自适应 (原始距离, 不紧缩)
- `calc_v45_tp(ohlcv, entry_idx, entry_price, signal, direction, all_signals)` — V464 多级TP: CHOCH > nearest swing > 20-bar swing > fib 1.272 > fib 1.618
- `_calc_entry_price_at_zone(ohlcv, entry_bar, sig, sig_dir)` — 价格区间入场计算 — 信号是范围(FVG/OB区域), 非单点。
- `evaluate_v45_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n, direction)` — V45统一入场评估 (POI激活 + V38出口)
- `calc_stock_params_v45(ohlcv, symbol)` — V464 每只股票自适应参数: ATR + BE/LK + SL紧缩乘数
- `backtest_stock_v45(ohlcv, symbol)` — V45单股票回测
- `run_backtest(symbols, label)` — V464 回测运行器 — SL紧缩×0.5 + Trailing×2宽松 + 多级TP + 宏观摆动

## hermes\scripts\v11\v464_engine_b.py
- `calc_v38_trailing(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V464 多目标trailing: 原始V463紧trailing + TP1到达后松
- `is_reversal_ob(ohlcv, sig, all_signals)` — 判断OB是否在结构反转处 (延续上升中的pullback不算)
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_atr_v45(ohlcv, idx, period)` — 
- `find_swing_highs(ohlcv, lookback)` — 
- `find_swing_lows(ohlcv, lookback)` — 
- `find_swing_high_forward(ohlcv, entry_idx, lookahead)` — 最近的前方摆动高
- `find_swing_low_forward(ohlcv, entry_idx, lookahead)` — 最近的前方摆动低
- `find_macro_swing_high(ohlcv, entry_idx, lookahead, lookback)` — V464: 20-bar宏观摆动高 — 捕获中期结构, 非局部小顶
- `find_macro_swing_low(ohlcv, entry_idx, lookahead, lookback)` — V464: 20-bar宏观摆动低
- `check_poi_activation(ohlcv, sig, entry_bar, direction)` — POI激活: 信号(如FVG/OB)的上下沿区域 = POI.
- `calc_v45_sl(ohlcv, entry_idx, entry_price, signal, entry_type, direction)` — V464 SL: 信号边界 > 摆动点 > ATR自适应 (原始距离, 不紧缩)
- `calc_v45_tp(ohlcv, entry_idx, entry_price, signal, direction, all_signals)` — V464 多级TP: CHOCH > nearest swing > 20-bar swing > fib 1.272 > fib 1.618
- `_calc_entry_price_at_zone(ohlcv, entry_bar, sig, sig_dir)` — 价格区间入场计算 — 信号是范围(FVG/OB区域), 非单点。
- `evaluate_v45_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n, direction)` — V45统一入场评估 (POI激活 + V38出口)
- `calc_stock_params_v45(ohlcv, symbol)` — V464 每只股票自适应参数: ATR + BE/LK + SL紧缩乘数
- `backtest_stock_v45(ohlcv, symbol)` — V45单股票回测
- `run_backtest(symbols, label)` — V464 回测运行器 — SL紧缩×0.5 + Trailing×2宽松 + 多级TP + 宏观摆动

## hermes\scripts\v11\v464_full_scan.py

## hermes\scripts\v11\v464_rr5_scan.py

## hermes\scripts\v11\v464_rr7_scan.py

## hermes\scripts\v11\v465_200_test.py

## hermes\scripts\v11\v465_engine.py
- `calc_v38_trailing(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V465 60min trailing — 5x宽松阈值, 允许多K线持仓
- `is_reversal_ob(ohlcv, sig, all_signals)` — 判断OB是否在结构反转处 (延续上升中的pullback不算)
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_atr_v45(ohlcv, idx, period)` — 
- `find_swing_highs(ohlcv, lookback)` — 
- `find_swing_lows(ohlcv, lookback)` — 
- `find_swing_high_forward(ohlcv, entry_idx, lookahead)` — 60min: 跳过8bar, 找远距离摆动高
- `find_swing_low_forward(ohlcv, entry_idx, lookahead)` — 60min: 跳过8bar, 找远距离摆动低
- `check_poi_activation(ohlcv, sig, entry_bar, direction)` — POI激活: 信号(如FVG/OB)的上下沿区域 = POI.
- `calc_v45_sl(ohlcv, entry_idx, entry_price, signal, entry_type, direction)` — V45 SL: 信号边界 > 摆动点 > ATR自适应
- `calc_v45_tp(ohlcv, entry_idx, entry_price, signal, direction, all_signals)` — V45 TP: 前方CHOCH > 前方摆动 > 无TP
- `_calc_entry_price_at_zone(ohlcv, entry_bar, sig, sig_dir)` — 价格区间入场计算 — 信号是范围(FVG/OB区域), 非单点。
- `evaluate_v45_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n, direction)` — V45统一入场评估 (POI激活 + V38出口)
- `calc_stock_params_v45(ohlcv, symbol)` — 计算每只股票自适应参数 (ATR + BE/LK)
- `backtest_stock_v45(ohlcv, symbol)` — V45单股票回测
- `run_backtest(symbols, label)` — 通用回测运行器

## hermes\scripts\v11\v465_full_scan.py

## hermes\scripts\v11\v466_200_test.py

## hermes\scripts\v11\v466_daily.py
- `calc_v38_trailing(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V38.4 差异化trailing + V42 BE/LK参数
- `is_reversal_ob(ohlcv, sig, all_signals)` — 判断OB是否在结构反转处 (延续上升中的pullback不算)
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_atr_v45(ohlcv, idx, period)` — 
- `find_swing_highs(ohlcv, lookback)` — 
- `find_swing_lows(ohlcv, lookback)` — 
- `find_swing_high_forward(ohlcv, entry_idx, lookahead)` — 最近的前方摆动高
- `find_swing_low_forward(ohlcv, entry_idx, lookahead)` — 最近的前方摆动低
- `check_poi_activation(ohlcv, sig, entry_bar, direction)` — POI激活: 信号(如FVG/OB)的上下沿区域 = POI.
- `calc_v45_sl(ohlcv, entry_idx, entry_price, signal, entry_type, direction)` — V45 SL: 信号边界 > 摆动点 > ATR自适应
- `calc_v45_tp(ohlcv, entry_idx, entry_price, signal, direction, all_signals)` — V45 TP: 前方CHOCH > 前方摆动 > 无TP
- `_calc_entry_price_at_zone(ohlcv, entry_bar, sig, sig_dir)` — 价格区间入场计算 — 信号是范围(FVG/OB区域), 非单点。
- `evaluate_v45_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n, direction)` — V45统一入场评估 (POI激活 + V38出口)
- `calc_stock_params_v45(ohlcv, symbol)` — 计算每只股票自适应参数 (ATR + BE/LK)
- `backtest_stock_v45(ohlcv, symbol)` — V45单股票回测
- `run_backtest(symbols, label)` — 通用回测运行器

## hermes\scripts\v11\v466_full_scan.py

## hermes\scripts\v11\v467_200_test.py

## hermes\scripts\v11\v467_engine.py
- `calc_v38_trailing(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V465 60min trailing — 5x宽松阈值, 允许多K线持仓
- `is_reversal_ob(ohlcv, sig, all_signals)` — 判断OB是否在结构反转处 (延续上升中的pullback不算)
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_atr_v45(ohlcv, idx, period)` — 
- `find_swing_highs(ohlcv, lookback)` — 
- `find_swing_lows(ohlcv, lookback)` — 
- `find_swing_high_forward(ohlcv, entry_idx, lookahead)` — 60min: 跳过8bar, 找远距离摆动高
- `find_swing_low_forward(ohlcv, entry_idx, lookahead)` — 60min: 跳过8bar, 找远距离摆动低
- `check_poi_activation(ohlcv, sig, entry_bar, direction)` — POI激活: 信号(如FVG/OB)的上下沿区域 = POI.
- `calc_v45_sl(ohlcv, entry_idx, entry_price, signal, entry_type, direction)` — V45 SL: 信号边界 > 摆动点 > ATR自适应
- `calc_v45_tp(ohlcv, entry_idx, entry_price, signal, direction, all_signals)` — V45 TP: 前方CHOCH > 前方摆动 > 无TP
- `_calc_entry_price_at_zone(ohlcv, entry_bar, sig, sig_dir)` — 价格区间入场计算 — 信号是范围(FVG/OB区域), 非单点。
- `evaluate_v45_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n, direction)` — V45统一入场评估 (POI激活 + V38出口)
- `calc_stock_params_v45(ohlcv, symbol)` — 计算每只股票自适应参数 (ATR + BE/LK)
- `backtest_stock_v45(ohlcv, symbol)` — V45单股票回测
- `run_backtest(symbols, label)` — 通用回测运行器

## hermes\scripts\v11\v467_full_scan.py

## hermes\scripts\v11\v468_200_test.py

## hermes\scripts\v11\v468_20_test.py

## hermes\scripts\v11\v468_engine.py
- `calc_v38_trailing(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V465 60min trailing — 5x宽松阈值, 允许多K线持仓
- `is_reversal_ob(ohlcv, sig, all_signals)` — 判断OB是否在结构反转处 (延续上升中的pullback不算)
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_atr_v45(ohlcv, idx, period)` — 
- `find_swing_highs(ohlcv, lookback)` — 
- `find_swing_lows(ohlcv, lookback)` — 
- `find_swing_high_forward(ohlcv, entry_idx, lookahead)` — 60min: 跳过3bar, 找前方摆动高
- `find_swing_low_forward(ohlcv, entry_idx, lookahead)` — 60min: 跳过3bar, 找前方摆动低
- `check_poi_activation(ohlcv, sig, entry_bar, direction)` — POI激活: 信号(如FVG/OB)的上下沿区域 = POI.
- `calc_v45_sl(ohlcv, entry_idx, entry_price, signal, entry_type, direction)` — V45 SL: 信号边界 > 摆动点 > ATR自适应
- `calc_v45_tp(ohlcv, entry_idx, entry_price, signal, direction, all_signals)` — V45 TP: 前方CHOCH > 前方摆动 > 无TP
- `_calc_entry_price_at_zone(ohlcv, entry_bar, sig, sig_dir)` — 价格区间入场计算 — 信号是范围(FVG/OB区域), 非单点。
- `evaluate_v45_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n, direction)` — V45统一入场评估 (POI激活 + V38出口)
- `calc_stock_params_v45(ohlcv, symbol)` — 计算每只股票自适应参数 (ATR + BE/LK)
- `backtest_stock_v45(ohlcv, symbol)` — V45单股票回测
- `run_backtest(symbols, label)` — 通用回测运行器

## hermes\scripts\v11\v468_full_scan.py

## hermes\scripts\v11\v469_engine.py
- `calc_signal_strength(sig, all_sigs_up_to_idx, ohlcv)` — 计算入场信号的强度等级 (A/B/C)
- `calc_v469_trailing(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V469 分级Trailing — 信号质量决定退出策略的宽松度。
- `is_reversal_ob(ohlcv, sig, all_signals)` — 反转OB检测 (同V468)
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_atr_v45(ohlcv, idx, period)` — 
- `find_swing_high_forward(ohlcv, entry_idx, lookahead)` — 60min: 跳过SWING_SKIP bar, 找前方摆动高
- `find_swing_low_forward(ohlcv, entry_idx, lookahead)` — 
- `check_poi_activation(ohlcv, sig, entry_bar, direction)` — 
- `calc_v469_sl(ohlcv, entry_idx, entry_price, signal, entry_type, direction)` — V469 SL: 信号边界 > 摆动点 > ATR自适应 (放宽边界范围)
- `calc_v469_tp(ohlcv, entry_idx, entry_price, signal, direction, all_signals)` — V469 TP — 保持结构TP作为trailing参考, 不再依赖其到达
- `_calc_entry_price_at_zone(ohlcv, entry_bar, sig, sig_dir)` — 同V468: 真实可成交入场价, 无虚假折扣
- `calc_stock_params_v469(ohlcv, symbol)` — 同V468参数
- `evaluate_v469_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n, direction)` — V469统一入场评估 — 多信号共振 + 分级trailing
- `backtest_stock_v469(ohlcv, symbol)` — V469单股票回测
- `run_backtest(symbols, label)` — 通用回测运行器
- `run_grid_search(symbols, param_grid)` — 网格搜索 — 扫描参数组合

## hermes\scripts\v11\v469_final.py
- `calc_v38_trailing(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V469-B 反向分级Trailing — Grade A紧/C松
- `calc_signal_strength(sig, all_sigs_up_to_idx, ohlcv)` — 计算入场信号的强度等级 (A/B/C)
- `is_reversal_ob(ohlcv, sig, all_signals)` — 判断OB是否在结构反转处 (延续上升中的pullback不算)
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_atr_v45(ohlcv, idx, period)` — 
- `find_swing_highs(ohlcv, lookback)` — 
- `find_swing_lows(ohlcv, lookback)` — 
- `find_swing_high_forward(ohlcv, entry_idx, lookahead)` — 60min: 跳过3bar, 找前方摆动高
- `find_swing_low_forward(ohlcv, entry_idx, lookahead)` — 60min: 跳过3bar, 找前方摆动低
- `check_poi_activation(ohlcv, sig, entry_bar, direction)` — POI激活: 信号(如FVG/OB)的上下沿区域 = POI.
- `calc_v45_sl(ohlcv, entry_idx, entry_price, signal, entry_type, direction)` — V45 SL: 信号边界 > 摆动点 > ATR自适应
- `calc_v45_tp(ohlcv, entry_idx, entry_price, signal, direction, all_signals)` — V45 TP: 前方CHOCH > 前方摆动 > 无TP
- `_calc_entry_price_at_zone(ohlcv, entry_bar, sig, sig_dir)` — 价格区间入场计算 — 信号是范围(FVG/OB区域), 非单点。
- `evaluate_v45_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n, direction)` — V45统一入场评估 (POI激活 + V38出口)
- `calc_stock_params_v45(ohlcv, symbol)` — 计算每只股票自适应参数 (ATR + BE/LK)
- `backtest_stock_v45(ohlcv, symbol)` — V45单股票回测
- `run_backtest(symbols, label)` — 通用回测运行器

## hermes\scripts\v11\v469_final_test.py

## hermes\scripts\v11\v469_full_scan.py

## hermes\scripts\v11\v469_grid_test.py

## hermes\scripts\v11\v469b_test.py

## hermes\scripts\v11\v469e_test.py

## hermes\scripts\v11\v469v2_200_test.py

## hermes\scripts\v11\v469v2_test.py

## hermes\scripts\v11\v469v3_200_test.py

## hermes\scripts\v11\v46_200_test.py

## hermes\scripts\v11\v46_engine.py
- `is_reversal_ob(ohlcv, sig, all_signals)` — 判断OB是否在结构反转处 (延续上升中的pullback不算)
- `find_retest_entry(ohlcv, sig, sig_idx, all_signals, direction)` — 价格回踩信号区域后入场
- `calc_v46_trailing(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V46 自适应trailing — 专为回踩入场优化
- `load_ohlcv(symbol)` — 
- `calc_atr_v46(ohlcv, idx, period)` — 
- `calc_stock_atr(ohlcv)` — 计算股票平均ATR%
- `short_trend(ohlcv, idx, lookback)` — 
- `find_swing_high_forward(ohlcv, entry_idx, lookahead)` — 
- `find_swing_low_forward(ohlcv, entry_idx, lookahead)` — 
- `calc_v46_tp(ohlcv, entry_idx, entry_price, signal, direction, all_signals)` — TP: 前方CHOCH > 前方摆动 > 无TP
- `evaluate_v46_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n, direction)` — V46统一入场评估 — 反转OB + 价格回踩 + 自适应trailing
- `calc_stock_params_v46(ohlcv, symbol)` — 
- `backtest_stock_v46(ohlcv, symbol)` — V46单股票回测
- `run_backtest(symbols, label)` — 

## hermes\scripts\v11\v46_full_scan.py

## hermes\scripts\v11\v470_engine.py
- `calc_v38_trailing(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V465 60min trailing — 5x宽松阈值, 允许多K线持仓
- `is_reversal_ob(ohlcv, sig, all_signals)` — 判断OB是否在结构反转处 (延续上升中的pullback不算)
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_atr_v45(ohlcv, idx, period)` — 
- `find_swing_highs(ohlcv, lookback)` — 
- `find_swing_lows(ohlcv, lookback)` — 
- `find_swing_high_forward(ohlcv, entry_idx, lookahead)` — 60min: 跳过3bar, 找前方摆动高
- `find_swing_low_forward(ohlcv, entry_idx, lookahead)` — 60min: 跳过3bar, 找前方摆动低
- `check_poi_activation(ohlcv, sig, entry_bar, direction)` — POI激活: 信号(如FVG/OB)的上下沿区域 = POI.
- `calc_v45_sl(ohlcv, entry_idx, entry_price, signal, entry_type, direction)` — V45 SL: 信号边界 > 摆动点 > ATR自适应
- `calc_v45_tp(ohlcv, entry_idx, entry_price, signal, direction, all_signals)` — V45 TP: 前方CHOCH > 前方摆动 > 无TP
- `_calc_entry_price_at_zone(ohlcv, entry_bar, sig, sig_dir)` — 价格区间入场计算 — 信号是范围(FVG/OB区域), 非单点。
- `evaluate_v45_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n, direction)` — V45统一入场评估 (POI激活 + V38出口)
- `calc_stock_params_v45(ohlcv, symbol)` — 计算每只股票自适应参数 (ATR + BE/LK)
- `backtest_stock_v45(ohlcv, symbol)` — V45单股票回测
- `run_backtest(symbols, label)` — 通用回测运行器

## hermes\scripts\v11\v472_200_test.py

## hermes\scripts\v11\v472_engine.py
- `calc_v38_trailing(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V465 60min trailing — 5x宽松阈值, 允许多K线持仓
- `is_reversal_ob(ohlcv, sig, all_signals)` — 判断OB是否在结构反转处 (延续上升中的pullback不算)
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_atr_v45(ohlcv, idx, period)` — 
- `find_swing_highs(ohlcv, lookback)` — 
- `find_swing_lows(ohlcv, lookback)` — 
- `find_swing_high_forward(ohlcv, entry_idx, lookahead)` — 60min: 跳过8bar, 找远距离摆动高
- `find_swing_low_forward(ohlcv, entry_idx, lookahead)` — 60min: 跳过8bar, 找远距离摆动低
- `check_poi_activation(ohlcv, sig, entry_bar, direction)` — POI激活: 信号(如FVG/OB)的上下沿区域 = POI.
- `calc_v45_sl(ohlcv, entry_idx, entry_price, signal, entry_type, direction)` — V45 SL: 信号边界 > 摆动点 > ATR自适应
- `calc_v45_tp(ohlcv, entry_idx, entry_price, signal, direction, all_signals)` — V45 TP: 前方CHOCH > 前方摆动 > 无TP
- `_calc_entry_price_at_zone(ohlcv, entry_bar, sig, sig_dir)` — 价格区间入场计算 — 信号是范围(FVG/OB区域), 非单点。
- `evaluate_v45_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n, direction)` — V45统一入场评估 (POI激活 + V38出口)
- `calc_stock_params_v45(ohlcv, symbol)` — 计算每只股票自适应参数 (ATR + BE/LK)
- `backtest_stock_v45(ohlcv, symbol)` — V45单股票回测
- `run_backtest(symbols, label)` — 通用回测运行器

## hermes\scripts\v11\v472_full_scan.py

## hermes\scripts\v11\v473_200_test.py

## hermes\scripts\v11\v473_engine.py
- `calc_v38_trailing(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V465 60min trailing — 5x宽松阈值, 允许多K线持仓
- `is_reversal_ob(ohlcv, sig, all_signals)` — 判断OB是否在结构反转处 (延续上升中的pullback不算)
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_atr_v45(ohlcv, idx, period)` — 
- `find_swing_highs(ohlcv, lookback)` — 
- `find_swing_lows(ohlcv, lookback)` — 
- `find_swing_high_forward(ohlcv, entry_idx, lookahead)` — 60min: 跳过8bar, 找远距离摆动高
- `find_swing_low_forward(ohlcv, entry_idx, lookahead)` — 60min: 跳过8bar, 找远距离摆动低
- `check_poi_activation(ohlcv, sig, entry_bar, direction)` — POI激活: 信号(如FVG/OB)的上下沿区域 = POI.
- `calc_v45_sl(ohlcv, entry_idx, entry_price, signal, entry_type, direction)` — V45 SL: 信号边界 > 摆动点 > ATR自适应
- `calc_v45_tp(ohlcv, entry_idx, entry_price, signal, direction, all_signals)` — V45 TP: 前方CHOCH > 前方摆动 > 无TP
- `_calc_entry_price_at_zone(ohlcv, entry_bar, sig, sig_dir)` — 价格区间入场计算 — 信号是范围(FVG/OB区域), 非单点。
- `evaluate_v45_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n, direction)` — V45统一入场评估 (POI激活 + V38出口)
- `calc_stock_params_v45(ohlcv, symbol)` — 计算每只股票自适应参数 (ATR + BE/LK)
- `backtest_stock_v45(ohlcv, symbol)` — V45单股票回测
- `run_backtest(symbols, label)` — 通用回测运行器

## hermes\scripts\v11\v473_full_scan.py

## hermes\scripts\v11\v474_engine.py
- `calc_v38_trailing(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V465 60min trailing — 5x宽松阈值, 允许多K线持仓
- `is_reversal_ob(ohlcv, sig, all_signals)` — 判断OB是否在结构反转处 (延续上升中的pullback不算)
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_atr_v45(ohlcv, idx, period)` — 
- `find_swing_highs(ohlcv, lookback)` — 
- `find_swing_lows(ohlcv, lookback)` — 
- `find_swing_high_forward(ohlcv, entry_idx, lookahead)` — 60min: 跳过8bar, 找远距离摆动高
- `find_swing_low_forward(ohlcv, entry_idx, lookahead)` — 60min: 跳过8bar, 找远距离摆动低
- `check_poi_activation(ohlcv, sig, entry_bar, direction)` — POI激活: 信号(如FVG/OB)的上下沿区域 = POI.
- `calc_v45_sl(ohlcv, entry_idx, entry_price, signal, entry_type, direction)` — V45 SL: 信号边界 > 摆动点 > ATR自适应
- `calc_v45_tp(ohlcv, entry_idx, entry_price, signal, direction, all_signals)` — V45 TP: 前方CHOCH > 前方摆动 > 无TP
- `_calc_entry_price_at_zone(ohlcv, entry_bar, sig, sig_dir)` — 价格区间入场计算 — 信号是范围(FVG/OB区域), 非单点。
- `evaluate_v45_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n, direction)` — V45统一入场评估 (POI激活 + V38出口)
- `calc_stock_params_v45(ohlcv, symbol)` — 计算每只股票自适应参数 (ATR + BE/LK)
- `backtest_stock_v45(ohlcv, symbol)` — V45单股票回测
- `run_backtest(symbols, label)` — 通用回测运行器

## hermes\scripts\v11\v475_engine.py
- `calc_v38_trailing(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V465 60min trailing — 5x宽松阈值, 允许多K线持仓
- `is_reversal_ob(ohlcv, sig, all_signals)` — 判断OB是否在结构反转处 (延续上升中的pullback不算)
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_atr_v45(ohlcv, idx, period)` — 
- `find_swing_highs(ohlcv, lookback)` — 
- `find_swing_lows(ohlcv, lookback)` — 
- `find_swing_high_forward(ohlcv, entry_idx, lookahead)` — 60min: 跳过8bar, 找远距离摆动高
- `find_swing_low_forward(ohlcv, entry_idx, lookahead)` — 60min: 跳过8bar, 找远距离摆动低
- `check_poi_activation(ohlcv, sig, entry_bar, direction)` — POI激活: 信号(如FVG/OB)的上下沿区域 = POI.
- `calc_v45_sl(ohlcv, entry_idx, entry_price, signal, entry_type, direction)` — V45 SL: 信号边界 > 摆动点 > ATR自适应
- `calc_v45_tp(ohlcv, entry_idx, entry_price, signal, direction, all_signals)` — V45 TP: 前方CHOCH > 前方摆动 > 无TP
- `_calc_entry_price_at_zone(ohlcv, entry_bar, sig, sig_dir)` — 价格区间入场计算 — 信号是范围(FVG/OB区域), 非单点。
- `evaluate_v45_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n, direction)` — V45统一入场评估 (POI激活 + V38出口)
- `calc_stock_params_v45(ohlcv, symbol)` — 计算每只股票自适应参数 (ATR + BE/LK)
- `backtest_stock_v45(ohlcv, symbol)` — V45单股票回测
- `run_backtest(symbols, label)` — 通用回测运行器

## hermes\scripts\v11\v476_engine.py
- `calc_v38_trailing(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V465 60min trailing — 5x宽松阈值, 允许多K线持仓
- `is_reversal_ob(ohlcv, sig, all_signals)` — 判断OB是否在结构反转处 (延续上升中的pullback不算)
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_atr_v45(ohlcv, idx, period)` — 
- `find_swing_highs(ohlcv, lookback)` — 
- `find_swing_lows(ohlcv, lookback)` — 
- `find_swing_high_forward(ohlcv, entry_idx, lookahead)` — 60min: 跳过8bar, 找远距离摆动高
- `find_swing_low_forward(ohlcv, entry_idx, lookahead)` — 60min: 跳过8bar, 找远距离摆动低
- `check_poi_activation(ohlcv, sig, entry_bar, direction)` — POI激活: 信号(如FVG/OB)的上下沿区域 = POI.
- `calc_v45_sl(ohlcv, entry_idx, entry_price, signal, entry_type, direction)` — V476 SL: 100% ATR自适应 (跳过所有边界/摆动点)
- `calc_v45_tp(ohlcv, entry_idx, entry_price, signal, direction, all_signals)` — V45 TP: 前方CHOCH > 前方摆动 > 无TP
- `_calc_entry_price_at_zone(ohlcv, entry_bar, sig, sig_dir)` — 价格区间入场计算 — 信号是范围(FVG/OB区域), 非单点。
- `evaluate_v45_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n, direction)` — V45统一入场评估 (POI激活 + V38出口)
- `calc_stock_params_v45(ohlcv, symbol)` — 计算每只股票自适应参数 (ATR + BE/LK)
- `backtest_stock_v45(ohlcv, symbol)` — V45单股票回测
- `run_backtest(symbols, label)` — 通用回测运行器

## hermes\scripts\v11\v477_engine.py
- `calc_v38_trailing(ohlcv, entry_idx, entry_price, initial_sl, structural_tp, n)` — V477 T+1-aware trailing — A股无法当日卖出
- `is_reversal_ob(ohlcv, sig, all_signals)` — 判断OB是否在结构反转处 (延续上升中的pullback不算)
- `load_ohlcv(symbol)` — 
- `short_trend(ohlcv, idx, lookback)` — 
- `calc_atr_v45(ohlcv, idx, period)` — 
- `find_swing_highs(ohlcv, lookback)` — 
- `find_swing_lows(ohlcv, lookback)` — 
- `find_swing_high_forward(ohlcv, entry_idx, lookahead)` — 60min: 跳过8bar, 找远距离摆动高
- `find_swing_low_forward(ohlcv, entry_idx, lookahead)` — 60min: 跳过8bar, 找远距离摆动低
- `check_poi_activation(ohlcv, sig, entry_bar, direction)` — POI激活: 信号(如FVG/OB)的上下沿区域 = POI.
- `calc_v45_sl(ohlcv, entry_idx, entry_price, signal, entry_type, direction)` — V476 SL: 100% ATR自适应 (跳过所有边界/摆动点)
- `calc_v45_tp(ohlcv, entry_idx, entry_price, signal, direction, all_signals)` — V45 TP: 前方CHOCH > 前方摆动 > 无TP
- `_calc_entry_price_at_zone(ohlcv, entry_bar, sig, sig_dir)` — 价格区间入场计算 — 信号是范围(FVG/OB区域), 非单点。
- `evaluate_v45_entry(all_signals, all_sigs_up_to_idx, sig, ohlcv, n, direction)` — V45统一入场评估 (POI激活 + V38出口)
- `calc_stock_params_v45(ohlcv, symbol)` — 计算每只股票自适应参数 (ATR + BE/LK)
- `backtest_stock_v45(ohlcv, symbol)` — V45单股票回测
- `run_backtest(symbols, label)` — 通用回测运行器

## hermes\scripts\v11\v500_structural_backtest.py
- `load_kline(symbol, cache_dir)` — 加载日线K线
- `collect_structural_tps(ohlcv, entry_idx, entry_price, swings, all_signals)` — 收集入场后所有结构阻力位作为TP候选
- `find_structural_sl(ohlcv, entry_idx, entry_price, swings, all_signals)` — V501修复: 仅用入场前(≤entry_idx)的结构支撑位
- `simulate_trade(ohlcv, entry_idx, entry_price, tp_levels, sl_info)` — 前向模拟: 逐bar检查是先触TP还是先触SL
- `backtest_stock(symbol)` — 对一只股票做结构TP/SL回测
- `aggregate_results(results)` — 汇总所有股票的回测结果
- `print_report(stats)` — 打印详细报告
- `main()` — 

## hermes\scripts\v11\v5_stock_viewer.py
- `fmt_date(d)` — 
- `short_label(t)` — 
- `build_v5_html(symbol)` — 

## hermes\scripts\v11\v9_mtf_engine.py
- `_calc_atr(closes, highs, lows, length)` — 计算ATR
- `check_weekly_trend(weekly)` — 周线趋势过滤: close > MA20 * (1 + 2%)
- `find_daily_entry(daily, zone_low, zone_high, sig_idx)` — 在日线上寻找回踩入场
- `find_hourly_entry(hourly, zone_low, zone_high, daily_sig_date)` — 在60min上寻找精确入场 (日线信号日期之后)
- `find_tp_target(daily, entry_idx, entry_price)` — 寻找TP目标: 前方swing_high (日线可达)
- `simulate_exit(daily, entry_idx, entry_price, sl, tp_price)` — 模拟trailing退出
- `backtest_stock_mtf(symbol, daily, weekly, hourly)` — 多周期联动回测单只股票
- `run_full_backtest(limit)` — 全量多周期回测

## hermes\scripts\v11\weekly_trend.py
- `synthesize_weekly(daily_ohlcv, bars_per_week)` — 从日线合成周线OHLCV
- `weekly_trend(weekly_ohlcv, lookback)` — 计算周线趋势方向
- `weekly_volatility(weekly_ohlcv, lookback)` — 周线波动率(ATR百分比)
- `weekly_daily_alignment(weekly_ohlcv, daily_ohlcv, end_idx, lookback)` — 检查周线和日线趋势是否对齐

## hermes\scripts\v11\wyckoff_phases_v38.py
- `detect_wyckoff_phases(ohlcv, structure_tree, lookback)` — Wyckoff 4阶段检测
- `get_phase_params(phase)` — 获取阶段自适应参数

## hermes\scripts\v11\zigzag_swings.py
- `detect_zigzag_swings(ohlcv, reversal_pct, use_high_low)` — 基于 zigzag 反转的摆动检测。

## hermes\scripts\v11_webui.py
- 类: V11Handler
- `run_analysis(symbol)` — 对一个股票运行完整的V11分析管道
- `main()` — 
- `do_GET(self)` — 
- `serve_html(self)` — 
- `analyze_symbol(self, symbol)` — 完整分析一个股票
- `system_status(self)` — 系统状态
- `limiter_stats(self)` — 
- `send_json(self, data, code)` — 
- `log_message(self, format)` — 

## hermes\scripts\v11_webui_v2.py
- 类: V11Handler
- `get_symbols()` — 
- `load_backtest_trades(symbol)` — 从回测结果加载该股票的交易
- `load_ohlcv(symbol)` — 从缓存加载OHLCV数据
- `detect_signals_for_chart(ohlcv, symbol)` — 运行V11信号检测并返回所有信号
- `main()` — 
- `do_GET(self)` — 
- `serve_html(self)` — 
- `serve_symbols(self)` — 
- `serve_trades(self, symbol)` — 为该股票返回回测交易记录
- `analyze_symbol(self, symbol)` — 
- `system_status(self)` — 
- `send_json(self, data, code)` — 
- `log_message(self, format)` — 

## hermes\scripts\v11_webui_v3.py
- 类: Handler
- `load_full_market()` — 加载V13所有批次结果
- `load_v14_optimized()` — 加载V14参数优化结果
- `load_ohlcv(symbol)` — 
- `get_symbols_with_backtest()` — 
- `get_symbols_with_v14()` — 
- `do_GET(self)` — 
- `handle_analyze(self, symbol)` — 
- `handle_market_overview(self)` — 
- `handle_optimized(self)` — 
- `send_html(self)` — 
- `send_json(self, data)` — 
- `send_error(self, code, msg)` — 
- `log_message(self, format)` — 

## hermes\scripts\v11_webui_v4.py
- 类: V4Handler
- `load_all_backtests()` — 
- `load_ohlcv(symbol)` — 
- `detect_signals_live(ohlcv, symbol)` — 实时信号检测
- `main()` — 
- `do_GET(self)` — 
- `serve_html(self, name)` — 
- `api_status(self)` — 
- `api_symbols(self, params)` — 
- `api_analyze(self, symbol)` — 
- `api_market_overview(self)` — 全量市场概览
- `api_versions(self)` — 全版本对比
- `api_trade_history(self, symbol, version)` — 
- `api_multi_param(self)` — 
- `send_json(self, data, code)` — 
- `log_message(self, format)` — 

## hermes\scripts\v14_viewer.py
- `load_ohlcv(symbol)` — 
- `fmt_date(d)` — 
- `build_v14(symbol, nav, signals_func)` — 

## hermes\scripts\v15_viewer.py
- `load_ohlcv(symbol)` — 
- `build_v15(symbol, nav)` — 

## hermes\scripts\v16_viewer.py
- `load_ohlcv(symbol)` — 
- `build_v16(symbol, nav)` — 

## hermes\scripts\v17_viewer.py
- `load_ohlcv(symbol)` — 
- `build_v17(symbol, nav)` — 

## hermes\scripts\v18_dashboard.py
- `build_v18(nav)` — 

## hermes\scripts\v25\_analyze_picks.py

## hermes\scripts\v25\advanced_smc.py
- `load_kline(symbol, weekly)` — 
- `compute_atr(klines, period, idx)` — 
- `find_swings(klines, lookback)` — Find recent swing highs and lows.
- `detect_turtle_soup(klines, entry_idx, atr)` — Detect Turtle Soup (false breakout) pattern at entry.
- `check_weekly_trend(symbol)` — HARD FILTER: only enter if weekly trend confirms direction.
- `run_v257_backtest()` — V25.7: Turtle Soup + CE + Weekly filter backtest.

## hermes\scripts\v25\audit_v47_1_p0_p11.py
- `load(p, d)` — 
- `f(x, d)` — 
- `i(x, d)` — 
- `kpath(sym)` — 
- `metrics(rows)` — 
- `bar_audit(trades)` — 
- `fvg_audit(trades)` — 
- `run()` — 

## hermes\scripts\v25\audit_v47_2_p0_p11.py
- `load(p, d)` — 
- `f(x, d)` — 
- `i(x, d)` — 
- `kpath(sym)` — 
- `bar_audit(rows)` — 
- `metrics(rows)` — 
- `main()` — 

## hermes\scripts\v25\audit_v47_pine_fvg.py
- `f(x, d)` — 
- `load(p, default)` — 
- `kpath(sym)` — 
- `audit_trade(t)` — 
- `run_one(name, path)` — 
- `main()` — 

## hermes\scripts\v25\audit_v47_smc_system.py
- `load_json(path, default)` — 
- `save_json(name, payload)` — 
- `f(x, default)` — 
- `i(x, default)` — 
- `date_key(x)` — 
- `kline_path(symbol)` — 
- `mtime_iso(path)` — 
- `metrics(rows)` — 
- `output_audit()` — 
- `current_signal_audit(limit_symbols)` — 
- `trade_autopsy()` — 
- `frontend_contract(base)` — 
- `run_all()` — 

## hermes\scripts\v25\audit_v47_unfinished_completion.py
- `load(p, default)` — 
- `text(path)` — 
- `http_json(path)` — 
- `has_regex(paths, pat)` — 
- `metrics(rows)` — 
- `main()` — 
- `f(x)` — 

## hermes\scripts\v25\audit_v47_wave_structure.py
- `load(p, d)` — 
- `f(x, d)` — 
- `audit_frontend(symbol)` — 
- `audit_trades(path)` — 
- `main()` — 

## hermes\scripts\v25\auto_fix.py
- `run(cmd, timeout)` — Run a command and return (exit_code, stdout).
- `auto_diagnose(trades_path)` — Analyze backtest results and return fix recommendations.
- `apply_fixes(fixes)` — Apply auto-fixes to state_backtest.py.
- `reload_frontend()` — Hit the /api/reload endpoint.
- `main()` — 

## hermes\scripts\v25\backtest_period_report.py
- `_num(value)` — 
- `_date(value)` — 
- `metrics(rows)` — 
- `_write_csv(path, rows)` — 
- `build_period_report(rows)` — 
- `write_period_reports(rows)` — 
- `main()` — 

## hermes\scripts\v25\backtest_v25.py
- `load_kline(symbol)` — 
- `find_entry_bar(klines, entry_date)` — Find the bar index matching entry_date in klines.
- `simulate_exit(pick, klines)` — Simulate exit for a single pick.
- `run_backtest(picks_path, output_path)` — Run backtest on all V25 picks.

## hermes\scripts\v25\backtest_v251.py
- `load_kline(symbol)` — 
- `find_entry_bar(klines, entry_date)` — 
- `compute_atr(klines, period, idx)` — 
- `fix_sltp(pick, klines)` — Apply V25.1 corrected SL/TP to a pick.
- `simulate_exit(pick, params, klines)` — Simulate exit with corrected SL/TP.
- `run_v251_backtest()` — V25.1: Fixed SL/TP + filtered entries

## hermes\scripts\v25\backups_smc_repair_20260522\smc_core_luxalgo_v34.py
- 类: PivotState
- `_f(x, default)` — 
- `_date(b)` — 
- `normalize(klines)` — 
- `true_ranges(klines)` — 
- `rolling_atr(klines, period)` — 
- `lux_leg_series(klines, size)` — Replicate LuxAlgo leg(size) state using high[size] > ta.highest(size).
- `lux_pivots(klines, size, level)` — 
- `display_structure_lux(klines, pivots, level)` — 
- `qualify_mss(events, sweeps, klines, atr, lookback)` — 
- `sweep_from_pivots(klines, pivots, atr, lookback, reclaim_atr, min_wick_ratio)` — 
- `order_blocks_from_structure(klines, events, atr)` — LuxAlgo-style order blocks created at structure break time.
- `detect_all_signals_lux_v34(klines, swing_len, internal_len)` — 

## hermes\scripts\v25\backups_smc_repair_20260522\smc_core_pine_like.py
- 类: Pivot, Trend
- `_f(x, default)` — 
- `_date(b)` — 
- `normalize_klines(klines)` — 
- `true_ranges(klines)` — 
- `rolling_atr(klines, period)` — 
- `adaptive_profile(klines, timeframe, override)` — 
- `pine_pivots(klines, size, use_left)` — Confirmed pivots using Pine-like right confirmation.
- `structure_state_machine(klines, pivots, atr, level, sweeps)` — 
- `_qualify_mss(events, sweeps, idx, direction, atr_val, klines)` — 
- `eqh_eql_signals(klines, eq_pivots, atr, threshold_mult)` — 
- `sweep_signals_stateful(klines, pivots, eqs, atr, profile)` — 
- `fvg_list_pine_like(klines, atr, profile)` — 
- `ob_signals_pine_like(klines, struct_events, atr, profile)` — 
- `bpr_signals_pine_like(fvgs, atr, profile)` — 
- `liquidity_voids(klines, atr, profile)` — 
- `ote_signals_from_struct(klines, struct_events, pivots)` — 
- `breaker_blocks_from_obs(klines, obs)` — Breaker blocks: failed OBs that price closes through and may later retest.
- `rejection_blocks_from_sweeps(klines, sweeps, atr)` — Rejection blocks derived from liquidity sweep rejection candles.
- `detect_all_signals_pine_like(klines, profile, timeframe)` — 
- `_empty_result(n)` — 
- `detect_all_signals_v32a(klines, profile, timeframe)` — 

## hermes\scripts\v25\backups_smc_repair_20260522\v41_final_engine.py
- `fdate(klines, i)` — 
- `symbol_from_filename(fp)` — 
- `_f(x, default)` — 
- `zone_invalidated_bull(bar, zl, close_buffer)` — Bullish demand/PD array invalidation before entry: close below zone low.
- `bar_touches_zone(bar, zl, zh, tolerance)` — 
- `next_retrace_strict(klines, start_idx, zl, zh, lookahead)` — Return first true zone touch after start_idx; reject if zone invalidates first.
- `confirm_at_zone_strict(klines, retrace_idx, zl, zh, max_confirm_bars)` — Require bullish rejection candle whose wick/body actually interacts with zone.
- `entry_from_limit_retouch(klines, conf_idx, zone, max_wait_bars, zone_type)` — 
- `dedupe_setups(setups)` — 
- `build_exit_plan(st, klines)` — 
- `backtest_v34_setups(setups, klines, max_hold_bars, min_hold_bars)` — 
- `find_prev_ssl(sweeps, ev_idx, lookback)` — 
- `is_liquidity_pool_sweep(sweep)` — 
- `choch_quality_ok(ev, sweep, zone_type, zone, klines, ri)` — 
- `find_recent_zone(signal_data, ev_idx, zone_type, sweep_idx)` — 
- `make_setup(symbol, arch, klines, signal_data, sweep, ev)` — 
- `build_v34_setups(symbol, klines, signal_data)` — 
- `process_stock(fp, start_date, end_date)` — 
- `metrics(trades)` — 
- `generate_picks(trades, max_recent_days)` — 
- `main(argv)` — 

## hermes\scripts\v25\batch_backtest.py
- `load_kline(symbol)` — 
- `find_entry_bar(klines, entry_date)` — 
- `compute_atr(klines, period, idx)` — 
- `find_structural_tp_targets(klines, entry_idx, entry_price)` — Find 2 structural TP targets above entry.
- `progressive_trail_buffer(r_multiple, atr)` — Tighten trail as profit increases.
- `simulate_batch_exit(pick, klines, state_params)` — Simulate batch TP + progressive trailing exit.
- `run_batch_backtest()` — Run V25.6 batch TP + progressive trailing backtest.

## hermes\scripts\v25\compact_story.py
- `extract_direction(seq_parts)` — Determine dominant direction: 'bull' or 'bear'
- `compact_story(ctx_seq, max_signals)` — Reduce a long ctx_seq to a compact 3-4 signal SMC story.
- `compact_all_picks(picks_path, output_path)` — Compact all picks' ctx_seq to short SMC stories.

## hermes\scripts\v25\daily_scan.py
- `_sig_type(s)` — 
- `_sig_bar(s)` — 
- `_sig_confidence(s)` — 
- `_sig_strength(s)` — 
- `_sig_meta(s)` — 
- `_sig_zone_low(s)` — 
- `_sig_zone_high(s)` — 
- `_detect_phase2_signals(klines)` — Use V22 signal engine for Phase2 production.
- `atr(klines, idx)` — 
- `ma(klines, idx, p)` — 
- `detect_state(klines, idx)` — 
- `compute_sltp(pick, klines)` — Compute SL/TP for a pick using V26 engine logic
- `_trend_ctx(klines, idx)` — 
- `_bull_fvgs(klines)` — 
- `_pass_daily_gate(zone_type, conf_type, score, trend_ctx, body_ratio)` — 
- `scan_last_bars(klines, symbol)` — Phase 2: SMC POI Retrace Entry Logic
- `main()` — 

## hermes\scripts\v25\diagnose_kline_refresh_source_cohorts.py
- `main()` — 

## hermes\scripts\v25\download_750.py
- `fetch_kline(code, market)` — 
- `save_kline(code, market, klines)` — 
- `main()` — 

## hermes\scripts\v25\engine_v25.py
- 类: V25Config
- `classify_volatility(atr_pct)` — Classify stock volatility from ATR%
- `compute_atr(klines, period, idx)` — Compute ATR from kline data at given index
- `load_kline_cache(symbol)` — Load daily kline cache
- `find_smart_money_cost(pick, klines)` — Identify smart money cost line from zone structure.
- `compute_dynamic_sltp(pick, klines, atr, atr_pct, entry_idx)` — V25 Dynamic SL/TP computation.
- `parse_v24_tp_tiers(tp_tiers_str)` — Parse V24 tp_tiers string like "BOS_level:9.4(9.3%)" or 
- `find_structural_tp_levels(pick, klines, entry_idx, entry_price)` — Multi-tier TP using V24 BOS/swing levels + structural scan.
- `compute_trailing_stop(entry_price, current_high, current_low, atr, pnl_r, trail_config)` — Update trailing stop based on price action.
- `run_v25_engine(picks, output_dir)` — Apply V25 dynamic SL/TP to picks and compute backtest results.

## hermes\scripts\v25\engine_v26.py
- `load_kline(symbol)` — 
- `compute_atr(klines, period, idx)` — 
- `compute_adx(klines, period, idx)` — 
- `detect_market_state(klines, entry_idx)` — 
- `compute_sltp(pick, klines, entry_idx, entry_price, atr, zone_lo)` — Compute multi-tier SL/TP with state-adaptive params + RR floor.
- `simulate_exit(pick, sltp, klines)` — Simulate exit with multi-tier TP (50% close + 50% trail).
- `run_v26_backtest()` — 

## hermes\scripts\v25\full_review_v24_v34.py
- `load(p)` — 
- `f(x, d)` — 
- `met(rows)` — 
- `group(rows, keyfn)` — 
- `quant(vals)` — 
- `q(p)` — 

## hermes\scripts\v25\full_scan.py
- `load_daily_kline(symbol)` — Load daily kline for a symbol.
- `detect_zone_and_entry(signals, klines, entry_idx)` — Detect the active zone and entry confirmation at entry_idx.
- `scan_single_stock(symbol, klines, params)` — Scan a single stock for V25 quality setups.
- `run_full_scan(limit, min_quality)` — Run full V25 scan on all stocks.

## hermes\scripts\v25\full_sync_closure_20260619.py
- `sh(cmd, timeout)` — 
- `get(path)` — 
- `raw(path)` — 
- `nonempty(v)` — 

## hermes\scripts\v25\mtf_resonance.py
- `load_kline(symbol, cache_dir, suffix)` — Load kline from cache. symbol: '000001.SZ'
- `weekly_trend_score(symbol)` — Analyze weekly trend for MTF resonance.
- `hourly_alignment_score(symbol, entry_date)` — Analyze 60min structure for entry timing alignment.
- `daily_structure_score(symbol, pick)` — Analyze daily chart structure quality.
- `compute_mtf_resonance(symbol, pick)` — Compute complete MTF resonance score 0-10.
- `run_mtf_analysis(picks)` — Run MTF resonance analysis on all picks.

## hermes\scripts\v25\p1_signal_audit_v35.py
- `sym(fp)` — 
- `main()` — 

## hermes\scripts\v25\p2_p4_diagnostics_v35.py
- `load(p)` — 
- `f(x)` — 
- `met(rows)` — 
- `group(rows, k)` — 
- `q(vals)` — 
- `pct(p)` — 

## hermes\scripts\v25\phase2_backtest.py
- `compute_atr(klines, bar, n)` — 
- `simulate(klines, entry_bar, entry_price, sl, tp1, symbol)` — 
- `metrics(trades, label)` — 

## hermes\scripts\v25\phase2_ld_audit_and_extract.py
- `key_date(v)` — 
- `metrics(ts)` — 
- `bucket(ts, fn)` — 
- `replay_all(limit)` — 
- `semantic_issues(t)` — 
- `add_review(t)` — 
- `main()` — 

## hermes\scripts\v25\phase2_ld_root_cause_audit.py
- `loadks(sym)` — 
- `close_below(ks, a, b, px)` — 
- `touch_count(ks, a, b, zl, zh)` — 
- `struct_ctx(ks, idx)` — 
- `discount_pos(ks, liq_bar, dbar, entry)` — 
- `bsl_target_rr(ks, entry_idx, entry, sl)` — 
- `pinbar_strength(ks, i)` — 
- `bucket(ts, fn)` — 
- `main()` — 

## hermes\scripts\v25\phase2_quality_backtest.py
- `compute_atr(klines, bar, n)` — 
- `ma(klines, idx, p)` — 
- `market_state(klines, idx)` — 
- `simulate(klines, entry_bar, entry_price, sl, tp1)` — 
- `main()` — 
- `bucket_report(name, keyfn)` — 
- `slbin(t)` — 
- `rbin(t)` — 
- `cbin(t)` — 
- `combo(label, fn)` — 
- `sbar(x)` — 

## hermes\scripts\v25\phase2_root_cause_audit.py
- `f(x)` — 
- `sim(ks, entry_idx, ep, sl, tp1, max_hold)` — 
- `metrics(rows)` — 
- `add(bucket, key, row)` — 
- `bucket_metrics(bucket)` — 
- `setup_universe(symbol, ks)` — 
- `replay_file(kf)` — 
- `binv(x, cuts, labels)` — 
- `main()` — 

## hermes\scripts\v25\phase2_smc_semantic_ablation.py
- `demand_pois_fixed(ks, lbar, dbar)` — 
- `entry_original(ks, poi, dbar)` — 
- `entry_inside_zone(ks, poi, dbar)` — 
- `entry_immediate_fvg(ks, poi, dbar)` — 
- `bsl_rr(ks, e, ep, sl)` — 
- `build(sym, ks, mode)` — 
- `bucket(ts, fn)` — 
- `main()` — 

## hermes\scripts\v25\phase2_strict_exit_audit.py
- `f(x)` — 
- `sbar(s)` — 
- `stype(s)` — 
- `slow(s)` — 
- `shigh(s)` — 
- `atr(ks, idx, n)` — 
- `state(ks, idx)` — 
- `sim_modes(ks, eb, ep, sl, tp1)` — 
- `replay(kf)` — 
- `met(ts)` — 
- `main()` — 

## hermes\scripts\v25\phase2_strict_ld_backtest.py
- `f(x)` — 
- `d(b)` — 
- `atr(ks, idx, n)` — 
- `is_swing_low(ks, i, left, right)` — 
- `is_swing_high(ks, i, left, right)` — 
- `swings_until(ks, upto, left, right)` — 
- `find_ssl_sweeps(ks)` — Bullish L event: wick below prior swing low/liquidity pool, close reclaimed.
- `find_displacement_after(ks, lbar, max_wait)` — D event: bullish close through latest pre-sweep swing high with ATR body.
- `demand_pois(ks, lbar, dbar)` — Demand created between liquidity sweep and displacement: OB first, FVG overlap optional.
- `find_reclaim_entry(ks, poi, dbar, max_wait)` — Wait for price to tap demand and reclaim it; enter on reclaim close.
- `simulate(ks, entry_idx, ep, sl, tp1, max_hold)` — 
- `build_setups(symbol, ks)` — 
- `replay_file(kf)` — 
- `metrics(ts)` — 
- `bucket(ts, fn)` — 
- `main()` — 

## hermes\scripts\v25\phase2_strict_ld_candidate.py
- `keep(t)` — 
- `date_order_ok(t)` — 
- `bucket(ts, fn)` — 
- `main()` — 

## hermes\scripts\v25\phase2_temporal_audit.py
- `f(x)` — 
- `d(b)` — 
- `sbar(s)` — 
- `stype(s)` — 
- `slow(s)` — 
- `shigh(s)` — 
- `atr(ks, idx, n)` — 
- `sim(ks, eb, ep, sl, tp)` — 
- `rec(symbol, ks, z, c, eb, mode)` — 
- `replay(kf)` — 
- `met(ts)` — 
- `main()` — 

## hermes\scripts\v25\phase2_wr_optimizer.py
- `f(x)` — 
- `d(b)` — 
- `atr(klines, idx, n)` — 
- `ma(klines, idx, p)` — 
- `state(klines, idx)` — 
- `simulate(klines, entry_idx, ep, sl, tp, max_hold)` — 
- `sig_bar(s)` — 
- `sig_type(s)` — 
- `sig_lower(s)` — 
- `sig_upper(s)` — 
- `sig_meta(s)` — 
- `is_safe_lux_ob(s)` — 
- `make_trade(symbol, klines, z, c, entry_idx, mode)` — 
- `trades_for_file(kf)` — 
- `metrics(ts)` — 
- `profile_report(trades)` — 
- `main()` — 

## hermes\scripts\v25\quarantine_diagnostic_monitor_state.py
- `load(p, default)` — 
- `save(p, data)` — 
- `quarantine_file(name, keep_fn)` — 
- `is_clean_position(r)` — 
- `is_clean_review(r)` — 
- `is_clean_ledger(r)` — 
- `main()` — 

## hermes\scripts\v25\refresh_daily_750.py
- `symbol_from_file(fp)` — 
- `out_path(code, market)` — 
- `latest_date(fp)` — 
- `parse_tencent(raw, code, market)` — 
- `tencent_market_is_open(raw)` — Read Tencent's market-status witness; do not trust host clock for a daily close.
- `parse_sina(raw)` — 
- `aligned_with_existing(path, rows, allow_latest_update)` — 
- `merge_new_rows(path, rows, replace_latest)` — 
- `write_atomic(path, rows)` — 
- `completed_market_cutoff(now)` — 
- `keep_completed_rows(rows, cutoff, market_open)` — 
- `evaluate_refresh_gate(requested, ok, latest_counts, before_latest_counts, now)` — Require a coherent, recent market date instead of request success alone.
- `fetch_one(item, stage_dir)` — 
- `valid_short_listing_history(rows, now)` — Accept a genuinely recent IPO history, never a one-bar provider truncation.
- `read_json(path, default)` — 
- `recover_incomplete_promotions()` — Rollback an interrupted promotion unless its current manifest was committed.
- `promote_epoch(epoch_id, stage_dir, successful, gate)` — Promote a gated epoch; current manifest is the final atomic commit point.
- `main()` — 

## hermes\scripts\v25\repair_monitor_duplicates.py
- `dk(v)` — 
- `load(name)` — 
- `save(name, data)` — 
- `backup(name)` — 

## hermes\scripts\v25\repair_t1_monitor_state.py
- `dk(v)` — 
- `load(name)` — 
- `save(name, rows)` — 
- `backup(name)` — 
- `main()` — 

## hermes\scripts\v25\resonance.py
- `download_60min(code)` — Download 60min klines for one stock from Tencent.
- `detect_60min_swings(klines)` — Detect swing highs/lows on 60min.
- `detect_60min_structure(klines)` — Detect market structure (bullish/bearish) on 60min.
- `detect_60min_fvg(klines)` — Detect FVG on 60min near current price.
- `assess_resonance(daily_pick, k60)` — Check if daily signal has 60min confirmation.
- `main(limit)` — Download 60min data for top picks and compute resonance.

## hermes\scripts\v25\scan_3y.py
- `scan_stock(kfile)` — Scan one stock for all entry opportunities across 3 years
- `main()` — 

## hermes\scripts\v25\signal_quality.py
- `parse_signal_sequence(ctx_seq)` — Parse a signal sequence string like:
- `score_signal_sequence(ctx_seq)` — Score signal sequence 0-10 based on SMC chain completeness.
- `score_zone_quality(zone_type, zone_age, detail, conf_type)` — Score zone quality 0-10.
- `score_entry_confirmation(conf_type, detail)` — Score entry confirmation quality 0-10.
- `score_mtf_resonance(entry_date, regime)` — Score multi-timeframe resonance 0-10.
- `compute_combined_quality(zone_score, seq_score, conf_score, mtf_score)` — Compute combined quality tier and multiplier.
- `score_all_picks(picks)` — Score all picks with V25.3 quality metrics.
- `run_v253_scoring(picks_path, output_dir)` — Run V25.3 quality scoring on picks.

## hermes\scripts\v25\smc_closed_loop_ops.py
- `now_cst()` — 
- `is_market_open(ts)` — 
- `append_log(name, rec)` — 
- `run_daily()` — 
- `call_json(path, timeout)` — 
- `run_live(force)` — 
- `run_postmarket()` — 
- `selftest()` — 
- `main()` — 

## hermes\scripts\v25\smc_core_luxalgo_v34.py
- 类: PivotState
- `_f(x, default)` — 
- `_date(b)` — 
- `normalize(klines)` — 
- `true_ranges(klines)` — 
- `rolling_atr(klines, period)` — 
- `lux_leg_series(klines, size)` — Replicate LuxAlgo leg(size) state.
- `wave_fractal_pivots(klines, size, level)` — Wave/Waves Ultimate style diagnostic pivots: left+right confirmed.
- `lux_pivots(klines, size, level)` — Active LuxAlgo leg(size) currentLevel pivots.
- `display_structure_lux(klines, pivots, level, wave_pivots, max_wave_distance)` — 
- `qualify_mss(events, sweeps, klines, atr, lookback)` — 
- `detect_independent_mss(internal_events, sweeps, klines, atr, lookback)` — 
- `sweep_from_pivots(klines, pivots, atr, lookback, reclaim_atr, min_wick_ratio)` — 
- `_wave_turn_ob_anchor(klines, wave_pivots, window, direction, max_dist)` — Return an OB candle anchored to a Waves-style HH/HL/LH/LL turn.
- `order_blocks_from_structure(klines, events, atr, wave_pivots)` — 
- `detect_all_signals_lux_v34(klines, swing_len, internal_len)` — 
- `nearest_wave(pidx, direction)` — 

## hermes\scripts\v25\smc_core_pine_like.py
- 类: Pivot, Trend
- `_f(x, default)` — 
- `_date(b)` — 
- `normalize_klines(klines)` — 
- `true_ranges(klines)` — 
- `rolling_atr(klines, period)` — 
- `adaptive_profile(klines, timeframe, override)` — 
- `pine_pivots(klines, size, use_left)` — Confirmed pivots using Pine-like right confirmation.
- `structure_state_machine(klines, pivots, atr, level, sweeps)` — 
- `_qualify_mss(events, sweeps, idx, direction, atr_val, klines)` — 
- `eqh_eql_signals(klines, eq_pivots, atr, threshold_mult)` — 
- `sweep_signals_stateful(klines, pivots, eqs, atr, profile)` — 
- `fvg_list_pine_like(klines, atr, profile)` — 
- `ob_signals_pine_like(klines, struct_events, atr, profile)` — Pine-quality OB detection.
- `bpr_signals_pine_like(fvgs, atr, profile)` — 
- `liquidity_voids(klines, atr, profile)` — 
- `ote_signals_from_struct(klines, struct_events, pivots)` — 
- `breaker_blocks_from_obs(klines, obs)` — Breaker blocks: failed OBs that price closes through and may later retest.
- `rejection_blocks_from_sweeps(klines, sweeps, atr)` — Rejection blocks derived from liquidity sweep rejection candles.
- `detect_all_signals_pine_like(klines, profile, timeframe)` — 
- `_empty_result(n)` — 
- `detect_all_signals_v32a(klines, profile, timeframe)` — 

## hermes\scripts\v25\smc_core_v27.py
- `confirmed_swings(klines, atr_period, left, right, noise_mult)` — Detect confirmed swing highs and lows.
- `structure_signals(klines, swings, atr_buffer)` — State-machine based BOS/CHOCH/MSS detection.
- `fvg_list(klines, min_gap)` — Detect 3-candle Fair Value Gaps.
- `bpr_signals(fvgs, struct_events, max_gap)` — BPR = opposing FVG overlap only.
- `sweep_signals(klines, swings, atr_buffer, lookback)` — Sweep must: pierce confirmed swing → close back inside → wick rejection.
- `ob_signals(klines, struct_events, max_back)` — OB must be anchored to a structure event (BOS/CHOCH/MSS).
- `ote_signals(klines, struct_events, swings)` — OTE = 0.62-0.79 retracement of the impulse leg created by BOS/CHOCH/MSS.
- `po3_signals(klines, sweeps, struct_events)` — PO3 = Accumulation → Manipulation (sweep) → Distribution (BOS/CHOCH).
- `compute_atr_pct(klines, idx, period)` — ATR as percentage of close at idx.
- `compute_ma(klines, idx, period)` — 
- `detect_all_signals_v27(klines)` — Run full signal detection pipeline.
- `_empty_result()` — 
- `is_zone_invalidated(klines, zone, up_to_idx)` — Check if a bullish zone has been invalidated (price closed below zone_low).
- `find_zone_for_event(signal_data, event_idx, zone_type)` — Find the zone (OB/BPR/OTE) anchored to a given structure event.
- `build_bullish_setups_v30(signal_data, klines, max_zone_age)` — V30 Correct SMC Sequence Builder:
- `build_bullish_setups(signal_data, klines, max_zone_age)` — Build complete bullish setups:
- `backtest_setups(setups, klines)` — Simulate trades from setups and return trade log.
- `compute_metrics(trades)` — 
- `export_chart_markers(signal_data, trades, symbol)` — Generate chart markers from signals for K-line display.

## hermes\scripts\v25\smc_core_v28.py
- `smart_money_cost_line(zone, klines, entry_idx)` — 
- `market_state(klines, idx)` — 
- `ob_grade(st, klines)` — 
- `ote_grade(st, klines)` — 
- `bpr_grade(st)` — 
- `event_chain_grade(st)` — 
- `cost_proximity_grade(st, klines)` — 
- `quality_score(st, klines)` — 
- `classify_signal(st, klines)` — 
- `enhance_setups(setups, klines)` — 
- `structural_sl(klines, st)` — 
- `adaptive_exit_plan(st, klines)` — 
- `backtest_quality_setups(setups, klines)` — 
- `resample_weekly(klines)` — 
- `computed_weekly_trend(klines, idx)` — 
- `daily_structure_alignment(signal_data, entry_idx)` — 
- `resonance_score(st, klines, signal_data)` — 
- `detect_build_backtest(klines, symbol)` — 

## hermes\scripts\v25\smc_core_v29.py
- `v29_enhance_setups(setups, klines)` — V29 quality pipeline: V28 scoring + V29 hard filters.
- `detect_build_backtest(klines, symbol)` — Full V29 pipeline: V27 detect → V28 scoring → V29 hard filters → backtest.

## hermes\scripts\v25\smc_daily_closed_loop.py
- `sh(cmd, cwd, timeout)` — 
- `active_version()` — 
- `smoke()` — 
- `main()` — 

## hermes\scripts\v25\smc_daily_ops.py
- `load(path, default)` — 
- `dkey(v)` — 
- `file_info(path)` — 
- `latest_market_date(refresh_result)` — Return only the market date of the committed production epoch.
- `refresh_is_usable(refresh_result)` — 
- `buy_valid_rows(rows)` — 
- `run_selector()` — 
- `run_shadow_selector()` — 
- `run_kline_refresh()` — 
- `run_daily_scan()` — 
- `run_v185_rematerialize()` — 
- `run_v365_shadow()` — Run the rejected V365 lineage as an isolated no-buy negative control.
- `run_production_registry()` — 
- `run_v231_shadow_audit()` — 
- `run_v236_shadow_audit()` — 
- `run_v246_shadow_audit()` — 
- `merge_latest_daily_scan_into_v66()` — 
- `build_log(selector_result, refresh_result, scan_result, merge_result, shadow_selector_result, v185_rematerialize_result)` — 
- `main()` — 
- `run_stage(cmd, timeout)` — 

## hermes\scripts\v25\smc_detector.py
- 类: Signal
- `atr(klines, idx, period)` — 
- `find_swings(klines, min_bars)` — Find swing highs and lows — more sensitive than LuxAlgo
- `detect_smc_signals(klines)` — Detects ONLY core SMC signals:
- `__repr__(self)` — 

## hermes\scripts\v25\smc_diagnostics_v28.py
- `exit_key(t_or_reason)` — Canonical exit reason for mixed V25-V29 outputs.
- `load_v28_data()` — Load V28 trades, picks, metrics.
- `cohort_by_exit_reason(trades)` — Worst cohorts by exit reason.
- `cohort_by_market_state(trades)` — Performance by market state.
- `cohort_by_zone_type(trades)` — Performance by zone type (OB/OTE/BPR).
- `cohort_by_quality_grade(trades)` — Performance by signal quality grades.
- `cohort_by_resonance(trades)` — Performance by MTF resonance alignment.
- `find_high_sl_groups(trades)` — Find clusters with abnormally high SL rate.
- `find_high_rr_groups(trades)` — Find clusters with highest RR.
- `_group_stats(trades, group_key_fn, min_n)` — Generic grouper: compute WR, SL rate, avg PnL, quality, top state, etc.
- `signal_ranking(trades)` — Comprehensive signal ranking by ctx_seq, zone×conf, grade, resonance, market.
- `signal_failure_attribution(trades)` — Root cause analysis: why do certain signal groups fail?
- `generate_fix_suggestions(trades)` — Auto-generate fix suggestions based on diagnostics.
- `write_diagnostics_report(trades, picks, metrics)` — Generate complete diagnostics report.
- `main()` — 

## hermes\scripts\v25\smc_morning_push.py
- `run_daily_preflight()` — Run refresh_daily_750 + daily_scan + ingest before building the push.
- `load_json(path, default)` — 
- `get_api(path, default)` — 
- `date_key(v)` — 
- `fmt_date(v)` — 
- `fmt_price(x)` — 
- `fmt_pct(x)` — 
- `safe(x, n)` — 
- `name(x)` — 
- `signal(x)` — 
- `md_table(headers, rows)` — 
- `pos_buy_date(p)` — 
- `pos_row(idx, p, live_by_sym)` — 
- `pick_status(p, held, pending)` — 
- `pick_row(idx, p, held, pending)` — 
- `main()` — 
- `sort_key(x)` — 

## hermes\scripts\v25\smc_production_registry.py
- `load(path, default)` — 
- `write_atomic(path, value)` — 
- `build_registry(epoch, v432, v433, v443)` — 
- `main()` — 

## hermes\scripts\v25\smc_signal_schema.py
- 类: ZoneSignal
- `_f(x, default)` — 
- `normalize_display_zone(raw_low, raw_high, atr, price, method, atr_mult)` — Return a visual-only normalized zone around the raw midpoint.
- `raw_zone(z)` — Extract raw trading zone from any legacy/new zone dict.
- `attach_raw_display_fields(z, atr, price)` — Mutate/copy a legacy zone to explicit raw/display fields.
- `to_dict(self)` — 

## hermes\scripts\v25\smc_sl_attribution.py
- `_f(x, default)` — 
- `classify_trade_sl(trade)` — 
- `summarize_attribution(trades)` — 

## hermes\scripts\v25\state_backtest.py
- `compute_adx(klines, period, idx)` — Compute ADX at given index.
- `detect_market_state(klines, entry_idx)` — Detect market state at entry time.
- `apply_state_params(pick, klines, state_info)` — Apply state-adaptive SL/TP/hold to a pick.
- `simulate_state_adaptive(pick, params, klines)` — Simulate exit with state-adaptive parameters.
- `run_state_backtest()` — Run backtest with state-adaptive parameters.

## hermes\scripts\v25\strict_smc_registry.py
- 类: StrictSignal
- `f(x, default)` — 
- `dt(bar)` — 
- `normalize_klines(klines)` — 
- `atr(klines, idx, period)` — 
- `confirmed_swings(klines, left, right)` — 
- `strict_structure(klines, swings)` — 
- `strict_fvgs(klines)` — 
- `nearest_bearish_candle(klines, event_idx, max_back)` — 
- `strict_obs(klines, structure)` — 
- `detect_strict_registry(klines)` — 
- `zone_retrace_rank(klines, zone, before_idx)` — 
- `to_dict(self)` — 

## hermes\scripts\v25\sync_phase2_to_v66.py

## hermes\scripts\v25\test_50_stocks.py

## hermes\scripts\v25\test_backtest_period_report.py
- `test_period_metrics_are_entry_date_based_and_do_not_filter_rows()` — 
- `test_period_artifacts_are_written_and_readable()` — 

## hermes\scripts\v25\test_deep_verify.py

## hermes\scripts\v25\test_frontend_field_contract_mpkfagiawk77km.py
- `blank(v)` — 
- `rows(payload)` — 
- `get_json(path)` — 
- `get_html(path)` — 
- `start_server()` — 
- `extract_table_rows(html)` — 
- `assert_nonblank(rows_, label, getter)` — 
- `test_api_picks_field_contract_zero_blank()` — 
- `test_api_live_prices_field_contract_zero_blank_and_numeric_volatility()` — 
- `test_monitor_html_current_picks_table_has_requested_columns_and_values()` — 
- `test_live_html_table_has_numeric_cost_zone_volatility()` — 
- `main()` — 

## hermes\scripts\v25\test_kline_markers_v88.py
- `load(sym)` — 
- `assert_trade_contract(sym)` — 

## hermes\scripts\v25\test_ob_multi.py

## hermes\scripts\v25\test_refresh_fail_closed.py
- `load(name)` — 
- `test_sina_parser_contract()` — 
- `test_ops_refresh_gate_is_fail_closed()` — 
- `test_ops_ingests_only_complete_buy_valid_rows()` — 
- `test_intraday_partial_daily_bar_is_excluded()` — 
- `test_failed_refresh_uses_only_committed_manifest_date()` — 
- `test_refresh_gate_rejects_stale_or_fragmented_latest_market_date()` — 
- `test_epoch_promotion_and_interrupted_rollback()` — 
- `test_partial_tencent_updates_only_latest_bar()` — 
- `test_open_market_witness_preserves_existing_bj_cache_in_stage()` — 
- `test_short_listing_history_is_explicitly_bounded()` — 
- `test_v365_shadow_stays_no_write_and_runs_independently()` — 

## hermes\scripts\v25\test_signal_fix.py

## hermes\scripts\v25\test_smc_frontend_registry_guard.py
- `load_module()` — 
- `test_empty_book_uses_latest_committed_cache_epoch()` — 
- `test_fail_closed_registry_uses_committed_epoch_not_stale_scanner_metadata()` — 
- `test_empty_book_converts_active_candidate_to_watch_only()` — 

## hermes\scripts\v25\test_smc_no_buy_valid_fail_closed.py
- `load(tmpdir)` — 
- `base_pick()` — 
- `test_each_missing_buy_authorization_field_fails_closed()` — 
- `test_complete_buy_valid_contract_can_reach_existing_t1_path()` — 
- `test_empty_book_registry_blocks_complete_looking_pick()` — 

## hermes\scripts\v25\test_v32b_engine.py
- `k(o, h, l, c, t)` — 
- `test_next_retrace_rejects_zone_invalidated_before_touch()` — 
- `test_next_retrace_requires_actual_zone_touch()` — 
- `test_confirm_at_zone_requires_rejection_at_zone_not_above_zone()` — 
- `test_make_entry_rejects_open_gap_above_zone_without_retouch()` — 
- `test_backtest_gap_through_stop_exits_at_open_not_stop_price()` — 
- `test_dedupe_keeps_best_quality_per_entry_zone_symbol()` — 

## hermes\scripts\v25\test_v32c_engine.py
- `bar(t, o, h, l, c)` — 
- `test_limit_entry_waits_for_zone_retouch_after_gap_above()` — 
- `test_limit_entry_rejects_no_retouch_chase()` — 
- `test_limit_entry_rejects_zone_invalidation_before_retouch()` — 
- `test_limit_entry_open_inside_zone()` — 

## hermes\scripts\v25\test_v437_target_first_dol.py
- `load_module()` — 
- `bar(o, h, l, c, t)` — 
- `test_dol_is_visible_before_event_and_nearest_unconsumed_target()` — 
- `test_lifecycle_requires_touch_then_later_reclaim_then_later_hold()` — 
- `test_dol_consumed_or_poi_invalidated_before_entry_cancels()` — 
- `test_right_edge_is_wait_not_entry_or_failure()` — 
- `test_semantic_order_uses_visibility_not_demand_candle_order()` — 

## hermes\scripts\v25\test_v438_target_first_dol_oracle.py
- `load_module()` — 
- `bar(o, h, l, c, t)` — 
- `test_target_selection_is_visible_nearest_and_unconsumed()` — 
- `test_lifecycle_requires_strictly_ordered_touch_reclaim_hold_and_entry()` — 
- `test_lifecycle_cancels_if_dol_or_poi_is_consumed()` — 
- `test_oracle_does_not_import_generator_or_v27()` — 

## hermes\scripts\v25\test_v439_target_first_dol_replay.py
- `load_module()` — 
- `bar(o, h, l, c, t)` — 
- `seed()` — 
- `test_target_first_dol_is_the_frozen_target_and_exit_starts_t1()` — 
- `test_same_bar_sl_tp_collision_is_conservative_stop()` — 
- `test_entry_must_be_next_bar_after_takeover()` — 

## hermes\scripts\v25\test_v440_protected_swing_transfer.py
- `load_module()` — 
- `bar(o, h, l, c, t)` — 
- `test_transfer_requires_newer_higher_confirmed_low_and_old_boundary_hold()` — 
- `test_lifecycle_uses_new_protected_low_as_hard_invalidation()` — 
- `test_poi_must_belong_to_transfer_leg_after_new_swing()` — 

## hermes\scripts\v25\test_v441_protected_swing_transfer_oracle.py
- `load_module()` — 
- `bar(o, h, l, c)` — 
- `test_independent_transfer_contract()` — 
- `test_oracle_does_not_import_generator_or_v27()` — 

## hermes\scripts\v25\test_v442_protected_swing_transfer_replay.py
- `load()` — 
- `bar(o, h, l, c, t)` — 
- `test_strict_t1_and_protected_low_stop()` — 
- `test_entry_chronology_must_be_next_session()` — 

## hermes\scripts\v25\test_v526_calendar_session_gate.py
- `test_weekday_lower_bound_sequence()` — 
- `test_later_open_allowed_only_after_proven_holiday_days()` — 
- `test_later_open_rejected_after_stale_symbol_on_open_day()` — 
- `test_exchange_suffix_controls_quote_prefix()` — 

## hermes\scripts\v25\test_v71_state_machine.py
- `bar(o, h, l, c, t)` — 
- `test_up_continuation_bos_pullback_to_discount_ob_reclaim_is_valid_story()` — 
- `test_downtrend_without_ssl_sweep_or_choch_rejects_demand_poi()` — 
- `test_ssl_sweep_then_choch_then_ob_reclaim_is_reversal_story()` — 

## hermes\scripts\v25\test_v74_environment_state_machine.py
- 类: TestV74EnvironmentStateMachine
- `test_bullish_breadth_with_negative_slope_and_rising_bear_is_distribution_not_bull(self)` — 
- `test_recovery_requires_bull_breadth_improving_from_compression_without_bear_dominance(self)` — 
- `test_violent_breadth_squeeze_after_bear_risk_is_distribution_not_recovery(self)` — 
- `test_bear_risk_overrides_discount_poi(self)` — 
- `test_continuation_story_requires_uptrend_bull_bos_and_reclaim(self)` — 
- `test_reversal_story_requires_recovery_or_accumulation_bull_choch_and_reclaim(self)` — 
- `test_fvg_solo_is_not_valid_demand_zone_even_in_good_environment(self)` — 

## hermes\scripts\v25\test_v76_environment_hysteresis.py
- `trade()` — 
- `bar(t, o, h, l, c)` — 
- `test_prior_distribution_blocks_single_day_fake_bull_continuation()` — 
- `test_stable_environment_with_acceptable_risk_passes_gate()` — 
- `test_risk_above_5p2_rejected_even_when_environment_is_stable()` — 
- `test_environment_risk_exit_obeys_t1_and_exits_before_later_stop()` — 

## hermes\scripts\v25\test_v78_smc_lifecycle_state_machine.py
- `bar(o, h, l, c, t)` — 
- `test_uptrend_bos_pullback_to_intact_poi_is_continuation_entry()` — 
- `test_downtrend_ssl_sweep_choch_pullback_is_reversal_entry_not_continuation()` — 
- `test_close_below_poi_is_real_invalidation_but_wick_retest_is_not()` — 
- `test_break_prior_hl_exits_as_trend_damage_even_if_poi_not_closed_below()` — 
- `test_nearest_bsl_hit_is_take_profit_target_before_structure_damage()` — 
- `test_late_bsl_after_actual_stop_horizon_does_not_relabel_loss_as_tp()` — 

## hermes\scripts\v25\test_v82_smart_money_quality_gate.py
- `base_candidate()` — 
- `test_accepts_context_first_deep_discount_delayed_reclaim()` — 
- `test_rejects_recovery_and_accumulation_until_true_recovery_is_proven()` — 
- `test_rejects_shallow_discount_poi()` — 
- `test_rejects_same_bar_or_one_bar_reclaim()` — 
- `test_rejects_uncontrolled_poi_width_and_bad_risk_band()` — 

## hermes\scripts\v25\test_v83_post_reclaim_takeover_gate.py
- `k(t, o, h, l, c)` — 
- `base_candidate()` — 
- `test_accepts_hold_above_poi_then_delays_entry_to_confirmation_next_open()` — 
- `test_accepts_higher_low_after_reclaim_even_if_close_not_strong()` — 
- `test_rejects_immediate_poi_close_break_after_reclaim()` — 
- `test_rejects_micro_hl_break_after_reclaim()` — 
- `test_rejects_when_no_next_open_after_takeover_confirmation()` — 

## hermes\scripts\v25\test_v84_smart_money_path_split_gate.py
- `base_row()` — 
- `test_accepts_continuation_only_when_hold_above_poi_and_market_stays_demand_valid()` — 
- `test_rejects_continuation_higher_low_takeover_as_weak_smart_money_control()` — 
- `test_rejects_continuation_when_environment_deteriorates_after_takeover()` — 
- `test_reversal_requires_ssl_sweep_story_and_hold_above_poi()` — 
- `test_rejects_reversal_without_meaningful_ssl_pierce()` — 
- `test_rejects_mixed_reversal_without_post_takeover_recovery_or_accumulation()` — 

## hermes\scripts\v25\test_v85_bear_risk_reversal_candidates.py
- `test_bear_risk_ssl_choch_reversal_is_promoted()` — 

## hermes\scripts\v25\test_v85_mixed_accumulation_generator.py
- `bar(t, o, h, l, c)` — 
- `test_mixed_narrow_poi_hold_above_is_accumulation_not_blocked()` — 
- `test_mixed_wide_poi_is_distribution_even_if_reclaimed()` — 
- `test_mixed_lower_low_after_reclaim_is_distribution()` — 
- `test_zone_width_pct_uses_zone_low_high_contract()` — 
- `test_generate_v85_expands_continuation_with_wider_bos_pullback_window()` — 

## hermes\scripts\v25\test_v86_production_gate.py
- `row()` — 
- `test_v86_keeps_v85_core_when_poi_is_tight_and_environment_not_recovery()` — 
- `test_v86_keeps_tight_recovery_rows_because_full_gate_must_keep_total_n_ge_500()` — 
- `test_v86_rejects_wide_poi_above_1_6_percent_because_rejected_bucket_has_double_poi_break_rate()` — 
- `test_v86_still_rejects_same_day_exit_for_t1()` — 
- `test_v86_still_requires_hold_above_poi_takeover()` — 

## hermes\scripts\v25\test_v87_mtf_entry_rr_matrix.py
- `test_find_m60_window_for_entry_date_uses_same_day_and_next_day_only()` — 
- `test_m60_reclaim_entry_uses_reclaim_close_and_intraday_swing_sl()` — 
- `test_compute_rr_rejects_invalid_or_tiny_risk()` — 
- `test_simulate_exit_legs_returns_tp1_tp2_runner_and_mfe_mae_r()` — 
- `test_daily_state_distinguishes_bull_recovery_and_bear_risk()` — 

## hermes\scripts\v25\test_v88_current_picks_contract.py
- `test_latest_batch_filter()` — 
- `test_v88_active_picks_are_current_month_scanner_candidates_not_backtest_reps()` — 

## hermes\scripts\v25\test_v88_executable_entry_contract.py
- `dk(v)` — 
- `load_kline(symbol)` — 
- `test_v88_entries_are_executable_on_entry_day()` — 

## hermes\scripts\v25\test_v89_recovery_known_target_repair.py
- `test_v89_uses_fixed_known_rr_target_not_liquidity_target()` — 
- `test_recovery_filter_removes_weak_recovery_and_accumulation()` — 
- `test_research_filters_are_marked_partial_60min()` — 
- `test_metrics_release_requirements_are_computable()` — 

## hermes\scripts\v25\test_v90_daily_full_market_scanner.py
- `load(name)` — 
- `test_v90_active_picks_have_frontend_contract_fields()` — 
- `test_v90_does_not_use_future_liquidity_target_as_plan()` — 
- `test_v90_t1_pick_to_join_guard()` — 
- `test_v90_report_matches_output_counts_and_field_audit()` — 

## hermes\scripts\v25\test_v91_shadow_zone_entry_scanner.py
- `load(name)` — 
- `test_v91_active_picks_have_frontend_contract_fields()` — 
- `test_v91_report_matches_outputs_and_zero_missing()` — 
- `test_v91_no_future_target_and_t1_guard()` — 
- `test_v91_gate_scope_is_shadow_not_v88_baseline()` — 
- `test_v91_active_picks_recovery_only_v93_secondary_gate_after_v93_audit()` — 

## hermes\scripts\v25\test_v92_recovery_time_stop_zone_mid_autopsy.py
- `report()` — 
- `test_scope_is_full_market_chain_not_top10_sample()` — 
- `test_zone_mid_entry_materially_reduces_one_bar_sl_vs_orig_chase_entry()` — 
- `test_recovery_loss_bucket_remains_unfit_for_blind_production()` — 
- `test_time_stop_high_mfe_is_capture_issue_not_signal_failure()` — 
- `test_zone_mid_not_promoted_to_baseline_but_risk_layer_passes_shadow_threshold()` — 

## hermes\scripts\v25\test_v93_recovery_time_runner_audit.py
- `ensure_report()` — 
- `test_recovery_gate_has_non_empty_recoverable_subbucket_and_rejects_rest()` — 
- `test_recovery_gate_is_structural_not_blanket_reenable()` — 
- `test_time_stop_runner_only_improves_high_mfe_time_stop_rows()` — 
- `test_runner_variant_improves_full_zone_mid_average_without_increasing_sl()` — 
- `test_core_risk_no_recovery_remains_production_quality_after_recovery_split()` — 

## hermes\scripts\v25\test_v96_adaptive_entry_exit_search.py
- `load_mod()` — 
- `test_v96_module_exists_and_exposes_universal_rules()` — 
- `test_v96_run_generates_full_market_non_stock_specific_report()` — 
- `test_v96_best_contract_has_year_stability_and_required_fields()` — 

## hermes\scripts\v25\test_v98_reachable_5r_probability_gate.py
- `load(name)` — 
- `test_v98_active_picks_have_frontend_contract_fields()` — 
- `test_v98_a_production_rr_gate()` — 

## hermes\scripts\v25\v100_economic_net_wr_gate.py
- `f(x, default)` — 
- `kline_path(symbol)` — 
- `load_ks_cache(rows)` — 
- `simulate_economic_exit(ks, row)` — 
- `v100_grade(tier)` — 
- `normalize_v100(r, ks)` — 
- `stat(rows)` — 
- `grouped(rows, field)` — 
- `year_stat(rows)` — 
- `missing(rows)` — 
- `main()` — 

## hermes\scripts\v25\v100_high_rr_gate.py
- `f(x, default)` — 
- `load(p, default)` — 
- `is_a_v98(r)` — 
- `weak_recovery(r)` — 
- `tier(r)` — 
- `grade(t)` — 
- `contract(x)` — 
- `stats(rows)` — 
- `group(rows, key)` — 
- `main()` — 

## hermes\scripts\v25\v100_search.py
- `kline_cached(symbol)` — 
- `f(x, d)` — 
- `metrics(rs)` — 
- `b(r, name)` — 

## hermes\scripts\v25\v100_structural_net_gate.py
- `fnum(x, default)` — 
- `is_a_v98(r)` — 
- `weak_environment(r)` — 
- `has_structure_contract(r)` — 
- `expected_net_at_tp2(r)` — 
- `expected_net_at_tp3(r)` — 
- `v100_tier(r)` — 
- `public_grade(tier)` — 
- `net_pnl(r)` — 
- `apply_frontend_contract(x)` — 
- `normalize_row(r)` — 
- `yearly(rows)` — 
- `stats(rows, include_years)` — 
- `field_missing(rows)` — 
- `main()` — 

## hermes\scripts\v25\v101_mtf_dna_combo_contract.py
- `load_json(path, default)` — 
- `fnum(x, default)` — 
- `dkey(v)` — 
- `sym_file_key(symbol)` — 
- `symbol_from_file_key(key)` — 
- `all_cached_symbols()` — 
- `kline_path(symbol, tf)` — 
- `load_klines(symbol, tf)` — 
- `rows_until(rows, date_key, tf)` — 
- `ma(vals, n)` — 
- `pivot_sequence(rows, lookback)` — 
- `tf_state(symbol, date_key, tf)` — 
- `mtf_contract(row)` — 
- `combo_key(row)` — 
- `build_dna(trades)` — 
- `enrich_row(row, dna)` — 
- `field_missing(rows)` — 
- `stats(rows)` — 
- `main()` — 

## hermes\scripts\v25\v102_balanced_volume_gate.py
- `load_json(path, default)` — 
- `fnum(x, default)` — 
- `dkey(v)` — 
- `sym_file_key(symbol)` — 
- `symbol_from_file_key(key)` — 
- `all_cached_symbols()` — 
- `kline_path(symbol, tf)` — 
- `load_klines(symbol, tf)` — 
- `rows_until(rows, date_key, tf)` — 
- `ma(vals, n)` — 
- `pivot_sequence(rows, lookback)` — 
- `tf_state(symbol, date_key, tf)` — 
- `mtf_contract(row)` — 
- `combo_key(row)` — 
- `build_dna(trades)` — 
- `enrich_row(row, dna)` — 
- `field_missing(rows)` — 
- `stats(rows)` — 
- `main()` — 

## hermes\scripts\v25\v103a_risk_gate.py
- `load_json(path, default)` — 
- `fnum(x, default)` — 
- `dkey(v)` — 
- `sym_file_key(symbol)` — 
- `symbol_from_file_key(key)` — 
- `all_cached_symbols()` — 
- `kline_path(symbol, tf)` — 
- `load_klines(symbol, tf)` — 
- `rows_until(rows, date_key, tf)` — 
- `ma(vals, n)` — 
- `pivot_sequence(rows, lookback)` — 
- `tf_state(symbol, date_key, tf)` — 
- `mtf_contract(row)` — 
- `combo_key(row)` — 
- `build_dna(trades)` — 
- `enrich_row(row, dna)` — 
- `field_missing(rows)` — 
- `stats(rows)` — 
- `main()` — 

## hermes\scripts\v25\v103a_stability_report.py
- `fnum(value, default)` — 
- `is_sl(row)` — 
- `is_win(row)` — 
- `date_key(row)` — 
- `month_key(row)` — 
- `load_prod(path)` — 
- `base_stats(rows)` — 
- `monthly_stats(rows)` — 
- `rolling_stats(rows, window)` — 
- `slice_stats(rows)` — 
- `analyze(name, rows)` — 
- `pct(value)` — 
- `md_table(headers, rows)` — 
- `main()` — 

## hermes\scripts\v25\v104_strict_reclaim_backtest.py
- `f(x, default)` — 
- `d(b)` — 
- `symbol_from_path(p)` — 
- `atr(ks, idx, n)` — 
- `ma(vals, n)` — 
- `pct(a, b)` — 
- `is_sw_low(ks, i, L, R)` — 
- `is_sw_high(ks, i, L, R)` — 
- `swings_until(ks, upto)` — 
- `confirmed_swings(ks)` — 
- `trend_context(ks, idx)` — 
- `find_ssl_sweeps(ks)` — 
- `find_bull_bos(ks, highs)` — 
- `displacement_after_sweep(ks, highs_all, lbar, max_wait)` — 
- `demand_fvg_near(ks, start_bar, event_bar)` — 
- `reclaim_after_touch(ks, poi, event_bar, max_wait)` — 
- `recent_swing_low(ks, lows_all, idx, fallback)` — 
- `simulate_exit(ks, eidx, ep, sl, tp1, tp2)` — 
- `make_row(symbol, ks, lows_all, family, event, poi)` — 
- `rows_for(symbol, ks)` — 
- `replay_file(path)` — 
- `metrics(rows)` — 
- `fvg_source_label(row)` — 
- `v116_gate_reason(row)` — 
- `bucket(rows, fn)` — 
- `semantic_audit(rows)` — 
- `interval_audit(rows)` — 
- `month_audit(rows)` — 
- `assign_pick_scope(rows)` — 
- `main()` — 
- `dist(vals)` — 

## hermes\scripts\v25\v105a_structural_tp2_reentry.py
- `fnum(x, default)` — 
- `dkey(v)` — 
- `nonempty(x)` — 
- `v104b_gate(row)` — 
- `v105a_gate(row)` — 
- `clean_sequence_gate(row)` — Hard audit only: do not accept same-day exits or event after entry.
- `stats(rows)` — 
- `by_year(rows)` — 
- `rolling_sl(rows, win)` — 
- `field_missing(rows, keys)` — 
- `failure_buckets(rows)` — 
- `main()` — 

## hermes\scripts\v25\v107_tradeable_regime_audit.py
- `f(x, default)` — 
- `pct(a, b)` — 
- `ymd_to_month(s)` — 
- `load_trades()` — 
- `load_kline_file(path)` — 
- `compute_full_market_stats(entry_dates)` — Compute ex-ante full-universe breadth for each entry date.
- `classify_regime(m)` — 
- `enrich(rows, market_stats)` — 
- `summarize(rows)` — 
- `summarize_shallow(rows)` — 
- `pass_rule(r, rule)` — 
- `build_matrix(rows)` — 
- `semantic_audit(rows)` — 
- `main()` — 

## hermes\scripts\v25\v107b_signal_semantic_audit.py
- `load_v107_module()` — 
- `f(x, default)` — 
- `bucket(v, cuts)` — 
- `shallow(rows)` — 
- `group(rows, key_fn, min_n)` — 
- `month_table(rows)` — 
- `enrich_rows()` — 
- `add_semantic_features(rows)` — 
- `bad_buckets(rows, min_n)` — 
- `concise_rows(rows, limit)` — 
- `candidate_rule(rows, name, pred)` — 
- `main()` — 

## hermes\scripts\v25\v107c_tradeable_regime_rederive.py
- `f(x, default)` — 
- `pct(a, b)` — 
- `winsor(v, lo, hi)` — 
- `bucket(v, cuts)` — 
- `load_trades()` — 
- `load_kline(path)` — 
- `compute_full_market_stats_750(entry_dates)` — 
- `classify_regime_v107c(m)` — 
- `shallow(rows)` — 
- `group(rows, key, min_n)` — 
- `add_features(rows)` — 
- `month_stats(rows)` — 
- `rule_summary(rows, name, pred)` — 
- `concise(rows)` — 
- `main()` — 

## hermes\scripts\v25\v108_bull_expansion_semantic_split.py
- `f(x, default)` — 
- `pct(a, b)` — 
- `metric(rows)` — 
- `group(rows, key)` — 
- `enrich_rows()` — 
- `concise(rows, limit)` — 
- `main()` — 

## hermes\scripts\v25\v109_range_transition_semantic_rebuild.py
- `f(x, default)` — 
- `pct(n, d)` — 
- `d(b)` — 
- `sym_path(symbol)` — 
- `load_kline(symbol)` — 
- `load_close_pairs(path)` — 
- `winsor(v, lo, hi)` — 
- `market_stats_750(entry_dates)` — 
- `classify_regime(m)` — 
- `atr(ks, idx, n)` — 
- `is_sw_high(ks, i, left, right)` — 
- `confirmed_highs(ks)` — 
- `second_structure_confirm(ks, event_idx, entry_idx, max_wait)` — 
- `summary(rows)` — 
- `group(rows, key, min_n)` — 
- `month_detail(rows)` — 
- `concise_trade(r)` — 
- `unique_symbol_date_rows(rows)` — 
- `duplicate_audit(rows)` — 
- `enrich_rows(rows)` — 
- `apply_v109_range_rule(r)` — 
- `main()` — 

## hermes\scripts\v25\v110_range_transition_dedup_failure_audit.py
- `f(x, default)` — 
- `i(x, default)` — 
- `pct(a, b)` — 
- `month(r)` — 
- `metric(rows)` — 
- `group(rows, key, min_n)` — 
- `dedup_symbol_entry(rows)` — Deterministic ex-ante canonical row per symbol+entry_date.
- `is_accept_8_21(r)` — 
- `is_accept_9_21(r)` — 
- `is_accept_second_only(r)` — 
- `is_accept_v109(r)` — 
- `loss_rows(rows)` — 
- `bin_risk(r)` — 
- `bin_retrace(r)` — 
- `bin_chase(r)` — 
- `concise(r)` — 
- `monthly(rows)` — 
- `main()` — 

## hermes\scripts\v25\v111_wait_structure_ontology_audit.py
- `f(x, default)` — 
- `i(x, default)` — 
- `pct(a, b)` — 
- `month(r)` — 
- `median(rows, key)` — 
- `avg(rows, key)` — 
- `metric(rows)` — 
- `dedup_symbol_entry(rows)` — 
- `join_v104(rows, v104_rows)` — 
- `feature_summary(name, rows)` — 
- `bucket(rows, key_fn)` — 
- `concise(r)` — 
- `main()` — 
- `row_line(s)` — 

## hermes\scripts\v25\v112_range_transition_generator_audit.py
- `f(x, default)` — 
- `i(x, default)` — 
- `pct(a, b)` — 
- `month(r)` — 
- `avg(rows, key)` — 
- `median(rows, key)` — 
- `enrich(r)` — 
- `metric(rows)` — 
- `dedup(rows, mode)` — 
- `summarize(name, rows)` — 
- `buckets(rows, key)` — 
- `concise(r)` — 
- `main()` — 
- `line(s)` — 

## hermes\scripts\v25\v113_mature_transition_loss_audit.py
- `f(x, default)` — 
- `i(x, default)` — 
- `pct(a, b)` — 
- `metric(rows)` — 
- `symbol_path(symbol)` — 
- `load_bars(symbol)` — 
- `enrich_indices(r)` — 
- `dedup_v110(rows)` — 
- `add_kline_context(row)` — 
- `summarize(name, rows)` — 
- `bucket(rows, key)` — 
- `concise(r)` — 
- `main()` — 
- `line(s)` — 

## hermes\scripts\v25\v114_fvg_demand_source_audit.py
- `f(x, default)` — 
- `i(x, default)` — 
- `d(bar)` — 
- `pct(a, b)` — 
- `symbol_path(symbol)` — 
- `load_bars(symbol)` — 
- `atr(ks, idx, n)` — 
- `enrich_indices(row)` — 
- `dedup_v110(rows)` — 
- `metric(rows)` — 
- `median(rows, key)` — 
- `source_label(row)` — 
- `add_source_context(row)` — 
- `bucket(rows, key)` — 
- `concise(row)` — 
- `main()` — 

## hermes\scripts\v25\v115_fvg_source_label_fullsample_audit.py
- `f(x, default)` — 
- `i(x, default)` — 
- `d(bar)` — 
- `pct(a, b)` — 
- `symbol_path(symbol)` — 
- `load_bars(symbol)` — 
- `atr(ks, idx, n)` — 
- `enrich_indices(row)` — 
- `dedup_v110(rows)` — 
- `metric(rows)` — 
- `median(rows, key)` — 
- `mean(rows, key)` — 
- `source_label(row)` — 
- `add_source_context(row)` — 
- `bucket(rows, key)` — 
- `month_table(rows, label)` — 
- `label_month_stability(rows)` — 
- `concise(row)` — 
- `md_bucket(lines, title, rows)` — 
- `main()` — 

## hermes\scripts\v25\v116_source_quality_gate_simulation.py
- `load_module(name, path)` — 
- `f(x, default)` — 
- `pct(a, b)` — 
- `metric(rows)` — 
- `delta(after, before)` — 
- `gate_hit(row)` — 
- `enrich_rows(rows)` — 
- `dedup(rows)` — 
- `split_sets(rows)` — 
- `simulation(rows)` — 
- `bucket(rows, fn)` — 
- `month_stability(rows)` — 
- `concise(r)` — 
- `run_full_market_rescan()` — 
- `md_metric_row(name, s)` — 
- `append_sim_section(lines, title, sim)` — 
- `append_month_section(lines, title, sim, limit)` — 
- `main()` — 

## hermes\scripts\v25\v117_source_gate_shadow_contract_audit.py
- `load_module(name, path)` — 
- `f(x, default)` — 
- `pct(num, den)` — 
- `metric(rows)` — 
- `gate_hit(row)` — 
- `enrich(rows)` — 
- `dedup(rows)` — 
- `gate_sim(rows)` — 
- `group_sim(rows, field)` — 
- `month_check(rows)` — 
- `rows_from_file(path)` — 
- `field_contract(rows)` — 
- `t1_audit(rows)` — 
- `fmt_metric(m)` — 
- `main()` — 

## hermes\scripts\v25\v118_v116_shadow_daily_scan_diff.py
- `load(path, default)` — 
- `f(x, default)` — 
- `key(r)` — 
- `scope_counts(rows)` — 
- `field_contract(rows)` — 
- `diff_keys(before, after)` — 
- `label_counts(rows)` — 
- `concise_row(r)` — 
- `strong_full_retrace(rows)` — 
- `main()` — 
- `row(items)` — 

## hermes\scripts\v25\v119_signal_supply_chain_audit.py
- `pct(part, whole)` — 
- `load_list(path)` — 
- `cdict(counter)` — 
- `interval(row, a, b)` — 
- `describe(vals)` — 
- `audit_generator()` — 
- `audit_existing_outputs()` — 
- `write_combo_csv(rows)` — 
- `main()` — 

## hermes\scripts\v25\v121_parallel_poi_continuation_stability_audit.py
- `f(x, default)` — 
- `d(b)` — 
- `date_s(x)` — 
- `load_json(p)` — 
- `kline_path(symbol)` — 
- `load_ks(symbol, cache)` — 
- `atr(ks, idx, n)` — 
- `idx_from_date(ks, day)` — 
- `demand_fvg_near(ks, start_bar, event_bar)` — 
- `reclaim_after_touch(ks, poi, event_bar, max_wait)` — 
- `overlap_pct(a_low, a_high, b_low, b_high)` — 
- `source_start_bar(row, event_bar)` — 
- `annotate_parallel_poi(rows, limit)` — 
- `pnl(row)` — 
- `metrics(rows)` — 
- `bucket(rows, fn)` — 
- `month_key(r)` — 
- `year_key(r)` — 
- `stability(rows)` — 
- `band(x, cuts, labels)` — 
- `main()` — 
- `poi_summary(rows)` — 

## hermes\scripts\v25\v122_shadow_parallel_poi_generator_audit.py
- `jload(path)` — 
- `symbol_from_path(path)` — 
- `v(b, key)` — 
- `ds(x)` — 
- `normalize_env(row)` — 
- `atr(ks, idx, n)` — 
- `overlap_pct(a_low, a_high, b_low, b_high)` — 
- `source_start_bar(event, event_idx)` — 
- `fvg_near_event(ks, event)` — 
- `enrich_poi_geometry(ks, event, poi, env)` — 
- `overlap_poi(ob, fvg)` — 
- `simulate_trade(c, ks)` — 
- `candidate_from_poi(symbol, ks, env, context, event, poi)` — 
- `event_records(symbol, ks, env_by_date)` — 
- `generate_parallel(symbol, ks, env_by_date)` — 
- `dedupe(rows)` — 
- `metrics(rows)` — 
- `bucket(rows, keyfn)` — 
- `stable(rows)` — 
- `v86_pass(r)` — 
- `write_csv(path, rows, fields)` — 
- `main()` — 

## hermes\scripts\v25\v123_source_specific_contract_search.py
- `ds(x)` — 
- `pct(n, d)` — 
- `metrics(rows)` — 
- `month_stability(rows)` — 
- `v86_pass(r)` — 
- `enrich_reclaim_geometry(rows, by_symbol_ks)` — 
- `build_rows()` — 
- `in_range(val, lo, hi)` — 
- `contract(name, source, pred, rows, min_n)` — 
- `search_demand_ob(rows)` — 
- `search_fvg(rows)` — 
- `search_ob_fvg(rows)` — 
- `write_csv(path, rows, fields)` — 
- `markdown_table_contracts(title, rows, limit)` — 
- `source_metrics(rows)` — 
- `main()` — 
- `pred(r, rr, ww, hm, fam, st)` — 
- `pred(r, mid, gap, rr, ww, rec)` — 
- `pred(r, ov, ww, rr, rec, hm)` — 

## hermes\scripts\v25\v123_source_specific_contract_search_fast.py
- `f(x, default)` — 
- `ds(x)` — 
- `load_rows()` — 
- `metrics(rows)` — 
- `stability(rows)` — 
- `inr(x, lo, hi)` — 
- `pack(name, source, hit, min_n)` — 
- `search(rows, source)` — 
- `write_csv(path, rows)` — 
- `table(title, rows, limit)` — 
- `main()` — 

## hermes\scripts\v25\v123_source_specific_contract_search_pandas.py
- `ds(s)` — 
- `load()` — 
- `metrics(d)` — 
- `stab(d)` — 
- `pack(source, name, d, min_n)` — 
- `add(out, source, name, d, min_n)` — 
- `search_demand(df)` — 
- `search_fvg(df)` — 
- `search_combo(df)` — 
- `write(path, rows)` — 
- `table(title, rows)` — 
- `main()` — 

## hermes\scripts\v25\v124_reclaim_strength_nohold_contract.py
- `metrics(rows)` — 
- `stable(rows)` — 
- `enrich_reclaim_fields(row, ks)` — 
- `dedupe_no_hold(rows)` — 
- `pack(name, rows, min_n)` — 
- `search_fvg(rows)` — 
- `write_csv(path, rows, fields)` — 
- `table(title, rows, n)` — 
- `main()` — 

## hermes\scripts\v25\v126_fvg_reclaim_shadow_readiness_audit.py
- `metrics(df)` — 
- `add_date_parts(df)` — 
- `table_metrics(groups)` — 
- `main()` — 

## hermes\scripts\v25\v128_parallel_scanner_candidate_audit.py
- `load_json(path)` — 
- `kline_path(symbol)` — 
- `bar_date(b)` — 
- `fbar(b, key)` — 
- `simulate(row, ks)` — 
- `metrics(rows)` — 
- `bucket(rows, keyfn)` — 
- `write_csv(path, rows)` — 
- `main()` — 

## hermes\scripts\v25\v129_fvg_scanner_contract_decomposition.py
- `metrics(df)` — 
- `add_recent_flag(df)` — 
- `mask_v125(df)` — 
- `breakdown_table(base, recent)` — 
- `single_clause_impact(base)` — 
- `fail_reason_counts(base)` — 
- `bucket_metrics(base)` — 
- `contract_search(base)` — 
- `write_md(summary)` — 
- `main()` — 

## hermes\scripts\v25\v129_v128_exit_target_diagnostic.py
- `num(x, default)` — 
- `date_key(x)` — 
- `bar_date(b)` — 
- `v(b, k)` — 
- `load_ks(sym)` — 
- `known_bsl(ks, entry_idx, entry_price, lookback)` — 
- `simulate_target(row, ks)` — 
- `metrics(rows, pnl, reason)` — 
- `bucket(rows, key)` — 

## hermes\scripts\v25\v130_fvg_demand_loss_semantic_replay.py
- `pct(a, b)` — 
- `symbol_to_cache(symbol)` — 
- `load_bars(symbol)` — 
- `bar_val(b, k)` — 
- `enrich_row(row, bars)` — 
- `metrics(df)` — 
- `bucket_table(df, field, bins, labels)` — 
- `compare_wl(df, fields)` — 
- `tag_loss(row)` — 
- `md_table(rows, cols)` — 
- `main()` — 
- `safe_bar(i)` — 

## hermes\scripts\v25\v130_target_rr_shadow_gate_audit.py
- `num(x, default)` — 
- `dk(x)` — 
- `met(rows)` — 
- `bucket(rows, key)` — 
- `pass_v130(r)` — 

## hermes\scripts\v25\v131_fvg_entry_execution_shadow_backtest.py
- `kline_path(symbol)` — 
- `load_json(path)` — 
- `fbar(b, key)` — 
- `pct(a, b)` — 
- `simulate_exit(row, bars, entry_idx, entry_price, reason_prefix)` — 
- `find_limit_entry(row, bars, limit_price, wait, label)` — 
- `has_real_reaction(row, bars)` — 
- `fake_recovery(row, bars)` — 
- `metrics(rows, pnl_key, exit_key)` — 
- `write_csv(path, rows)` — 
- `bucket(rows, keyfn, pnl_key, exit_key)` — 
- `main()` — 

## hermes\scripts\v25\v131_strict_reclaim_ob_research_gate.py
- `num(x, d)` — 
- `dk(x)` — 
- `met(rs)` — 
- `bucket(rs, key)` — 
- `pass_gate(r)` — 

## hermes\scripts\v25\v132_fvg_reclaim_takeover_shadow_backtest.py
- `kline_path(symbol)` — 
- `load_json(path)` — 
- `fbar(b, key)` — 
- `pct(a, b)` — 
- `metrics(rows, pnl_key, exit_key)` — 
- `bucket(rows, keyfn, pnl_key, exit_key)` — 
- `write_csv(path, rows)` — 
- `calc_reclaim_features(row, bars)` — 
- `true_takeover(row, n, strict)` — 
- `failed_reclaim(row, n)` — 
- `classify(row)` — 
- `simulate_delayed_entry(row, bars, n, label)` — 
- `main()` — 

## hermes\scripts\v25\v133_realtime_quality_failed_reclaim_gate.py
- `metrics(df, pnl_col, exit_col)` — 
- `add_t0_score(df)` — 
- `slice_metrics(df, slices)` — 
- `delayed_metrics(delayed)` — 
- `production_snapshot()` — 
- `md_table(rows, cols)` — 
- `main()` — 

## hermes\scripts\v25\v134_candidate_timing_lifecycle_shadow_audit.py
- `metrics(df, pnl_col, exit_col)` — 
- `delayed_metrics()` — 
- `md_table(rows, cols)` — 
- `production_snapshot()` — 
- `recent_window_counts(df)` — 
- `main()` — 

## hermes\scripts\v25\v135_lifecycle_shadow_field_export.py
- `safe_num(v)` — 
- `api_json(path)` — 
- `metrics(df)` — 
- `lifecycle_export_status(row)` — 
- `cancel_reason(row)` — 
- `row_to_contract(row)` — 
- `coverage(df)` — 
- `main()` — 

## hermes\scripts\v25\v136_lifecycle_ui_api_dry_run_mapping.py
- `load_rows(name)` — 
- `fetch_json(path)` — 
- `production_snapshot()` — 
- `ui_row(row)` — 
- `build_payload(rows, scope)` — 
- `validate_payload(payload)` — 
- `latest_duplicate_count(rows)` — 
- `write_report(summary)` — 
- `main()` — 

## hermes\scripts\v25\v138_keep_watch_strong_executable_semantic_audit.py
- `num(x, default)` — 
- `date_key(x)` — 
- `pct(a, b)` — 
- `fbar(b, k)` — 
- `load_rows(path)` — 
- `write_csv(path, rows)` — 
- `kline_path(symbol)` — 
- `metrics(rows, pnl_key)` — 
- `bucket(rows, key)` — 
- `is_bool_true(v)` — 
- `is_strong_shadow(r)` — 
- `tp_levels(row, bars, entry_idx)` — 
- `simulate(row, bars, mode)` — 
- `main()` — 

## hermes\scripts\v25\v139_keep_watch_strong_semantic_hardening.py
- `b(v)` — 
- `num(s)` — 
- `metrics(df)` — 
- `row(name, df)` — 
- `main()` — 

## hermes\scripts\v25\v140_zone_close_dead_kline_replay.py
- `to_num(s)` — 
- `bools(s)` — 
- `pct(a, b)` — 
- `cache_path(symbol)` — 
- `load_bars(symbol)` — 
- `bv(bar, k)` — 
- `datev(bar)` — 
- `metrics(df)` — 
- `enrich(row, bars)` — 
- `gate_table(df, gates)` — 
- `main()` — 
- `bar(i)` — 

## hermes\scripts\v25\v140_zone_close_dead_kline_semantic_replay.py
- `bool_s(s)` — 
- `num(s)` — 
- `fnum(v, default)` — 
- `pct(a, b)` — 
- `metrics(df)` — 
- `kline_path(symbol)` — 
- `load_bars(symbol)` — 
- `bar_date(b)` — 
- `enrich_row(r)` — 
- `bucket_rows(df)` — 
- `main()` — 
- `get(i, key)` — 

## hermes\scripts\v25\v141_v140_lead_timing_availability.py
- `bool_s(s)` — 
- `num(s)` — 
- `metrics(df)` — 
- `row_metrics(name, df)` — 
- `production_probe()` — 
- `classify_timing(row)` — Earliest possible availability for V140 lead components.
- `component_table(df)` — 
- `main()` — 

## hermes\scripts\v25\v142_no_lag_entry_gap_filter_audit.py
- `bool_s(s)` — 
- `num(s)` — 
- `metrics(df)` — 
- `with_delta(row, base)` — 
- `production_probe()` — 
- `candidate_masks(df)` — 
- `main()` — 

## hermes\scripts\v25\v143_late_known_lifecycle_metadata_export.py
- `bool_s(s)` — 
- `num(s)` — 
- `metrics(df)` — 
- `production_probe()` — 
- `lifecycle_status(row)` — 
- `reason(row)` — 
- `main()` — 

## hermes\scripts\v25\v144_v143_ui_api_dry_run_mapping.py
- `load_rows(name)` — 
- `fetch_json(path)` — 
- `production_snapshot()` — 
- `ui_row(row)` — 
- `build_payload(rows, scope)` — 
- `validate_payload(payload)` — 
- `duplicate_count(rows, keys)` — 
- `write_report(summary)` — 
- `main()` — 

## hermes\scripts\v25\v147_v144_preview_integrity_replay.py
- `fnum(v, default)` — 
- `pct(a, b)` — 
- `bar_date(b)` — 
- `kline_path(symbol)` — 
- `load_bars(symbol)` — 
- `get_bar_value(bars, idx, key)` — 
- `recompute(row)` — 
- `load_payload(scope)` — 
- `fetch_raw(path)` — 
- `production_probe()` — 
- `audit_scope(scope)` — 
- `main()` — 

## hermes\scripts\v25\v148_readonly_lifecycle_contract_audit.py
- `fetch(path)` — 
- `json_fetch(path)` — 
- `audit_preview(scope)` — 
- `audit_page()` — 
- `audit_prod()` — 
- `main()` — 

## hermes\scripts\v25\v149_lifecycle_exit_backtest.py
- `fnum(v, default)` — 
- `bseries(s)` — 
- `pct(a, b)` — 
- `date_key(v)` — 
- `bar_date(bar)` — 
- `load_bars(symbol)` — 
- `bar_val(b, key)` — 
- `metrics(df, pnl_col)` — 
- `original_baseline_row(row)` — 
- `lifecycle_status(row)` — Derive the same lifecycle metadata as V143 from V140/V141 fields.
- `lifecycle_exit_row(row, variant)` — 
- `by_group(df, key)` — 
- `monthly(df)` — 
- `main()` — 

## hermes\scripts\v25\v150_lifecycle_exit_tradeoff_anatomy.py
- `fnum(s)` — 
- `bseries(s)` — 
- `metrics(df, pnl_col)` — 
- `group_metrics(df, key)` — 
- `make_pair(df, variant)` — 
- `main()` — 

## hermes\scripts\v25\v150_lifecycle_sl_adjust_backtest.py
- `fnum(v, default)` — 
- `bseries(s)` — 
- `pct(a, b)` — 
- `date_key(v)` — 
- `bar_date(bar)` — 
- `load_bars(symbol)` — 
- `bar_val(b, key)` — 
- `metrics(df, pnl_col)` — 
- `lifecycle_status(row)` — 
- `original_baseline_row(row)` — 
- `find_structure_sl_idx(bars, entry_idx, entry_price)` — Return idx of the bar where price hits entry_price - ~3% (structure SL).
- `find_breakeven_sl_hit_idx(bars, sl_start_idx, sl_price)` — Return idx where low <= sl_price from sl_start_idx onward.
- `find_v138_exit_info(row)` — Get the original V138 exit info for a row.
- `build_v150_row(row, variant, bars)` — Build one V150 variant row from input row.
- `by_group(df, key)` — 
- `monthly(df)` — 
- `main()` — 

## hermes\scripts\v25\v151_observation_window_sl.py
- `fnum(v, default)` — 
- `bseries(s)` — 
- `pct(a, b)` — 
- `date_key(v)` — 
- `bar_date(bar)` — 
- `load_bars(symbol)` — 
- `bar_val(b, key)` — 
- `metrics(df, pnl_col)` — 
- `lifecycle_status(row)` — 
- `original_baseline_row(row)` — 
- `find_obs_window_sl_hit(bars, entry_idx, entry_price, obs_window, sl_pct, profit_threshold_pct)` — Observation window SL logic.
- `build_v151_row(row, variant, bars)` — 
- `by_group(df, key)` — 
- `monthly(df)` — 
- `main()` — 

## hermes\scripts\v25\v152_apply_production_artifacts.py
- `fnum(v, default)` — 
- `ikey(v)` — 
- `bval(v)` — 
- `metrics(rows)` — 
- `bucket(rows, key, prefix)` — 
- `convert_row(row)` — 
- `main()` — 

## hermes\scripts\v25\v152_hybrid_lifecycle_gate.py
- `bseries(s)` — 
- `metrics(df, pnl_col)` — 
- `as_v152(row, threshold)` — 
- `group_metrics(df, key)` — 
- `main()` — 

## hermes\scripts\v25\v153_volume_micro_pnl_audit.py
- `bseries(s)` — 
- `fnum_series(df, col, default)` — 
- `normalize_base(df)` — 
- `normalize_v152(df)` — 
- `metrics(df)` — 
- `yearly_metrics(df, variant)` — 
- `bucket_metrics(df, variant, key)` — 
- `main()` — 

## hermes\scripts\v25\v154_cancel_addback_no_micro.py
- `fnum(df, col, default)` — 
- `bseries(df, col)` — 
- `prep(df)` — 
- `metrics(df)` — 
- `yearly(df, variant)` — 
- `main()` — 

## hermes\scripts\v25\v155_v154_stability_audit.py
- `fnum(df, col, default)` — 
- `metrics(df)` — 
- `main()` — 

## hermes\scripts\v25\v156_market_breadth_regime_audit.py
- `fnum(v, default)` — 
- `fseries(df, col)` — 
- `date_key(bar)` — 
- `metrics(df, pnl_col)` — 
- `main()` — 

## hermes\scripts\v25\v157_2024_weak_month_root_cause_audit.py
- `fnum(v, default)` — 
- `bval(v)` — 
- `sdate(v)` — 
- `month_key(v)` — 
- `metrics(df)` — 
- `load_bars(symbol)` — 
- `bar_date(b)` — 
- `add_symbol_context(row)` — 
- `root_flags(row)` — 
- `main()` — 

## hermes\scripts\v25\v158_non_leak_smc_lifecycle_rebuild.py
- `fnum(v, default)` — 
- `bool_s(s)` — 
- `num_s(s, default)` — 
- `date_key(v)` — 
- `metrics(df, pnl_col)` — 
- `release_pass(m)` — 
- `loss_table(df, limit)` — 
- `main()` — 

## hermes\scripts\v25\v159_v158_stability_fragility_audit.py
- `bool_s(s)` — 
- `num_s(s, default)` — 
- `date_key(v)` — 
- `add_time_cols(df)` — 
- `metrics(df, pnl_col)` — 
- `release_pass(m)` — 
- `group_metrics(df, group_col)` — 
- `rolling_metrics(df, window)` — 
- `loss_buckets(df)` — 
- `threshold_sensitivity(base)` — 
- `main()` — 

## hermes\scripts\v25\v160_v158_robust_monthly_rule_search.py
- `bool_s(s)` — 
- `num_s(s, default)` — 
- `date_key(v)` — 
- `add_time(df)` — 
- `metrics(df)` — 
- `release(m)` — 
- `monthly_bad(df)` — 
- `rolling_bad(df, window)` — 

## hermes\scripts\v25\v161_dry_run_scanner_contract.py
- `load_json(path, default)` — 
- `kline_path(symbol)` — 
- `row_has_outcome_field(row)` — 
- `missing_required(row, fields)` — 
- `apply_v158(row)` — 
- `apply_v160(row)` — 
- `build_row(src, bars)` — 
- `field_audit(rows)` — 
- `write_csv(path, rows)` — 
- `main()` — 

## hermes\scripts\v25\v162_v160_weak_month_attribution.py
- `num_s(s, default)` — 
- `bool_s(s)` — 
- `date_key(v)` — 
- `add_time(df)` — 
- `metrics(df)` — 
- `monthly_metrics(df)` — 
- `release_gate(m, bad60)` — 
- `safe_numeric_features(df)` — 
- `single_filter_search(df)` — 
- `compact_combo_search(df)` — 
- `weak_month_row_dump(df, md)` — 
- `loss_attribution(df)` — 
- `main()` — 

## hermes\scripts\v25\v163_scanner_rule_integrity_audit.py
- `num_s(s, default)` — 
- `bool_s(s)` — 
- `load_json_df(path)` — 
- `classify_integrity(df)` — 
- `vc(series, limit)` — 
- `slim_rows(df)` — 
- `main()` — 

## hermes\scripts\v25\v164_corrected_scanner_dry_run.py
- `boolish(value)` — 
- `apply_v164(row)` — 
- `enrich_v164(row)` — 
- `vc(rows, key)` — 
- `write_csv(path, rows)` — 
- `slim(row)` — 
- `main()` — 

## hermes\scripts\v25\v164_v153_pre_promotion_audit.py
- `load_json(path, default)` — 
- `fnum(df, col, default)` — 
- `bool_series(df, col)` — 
- `metrics(df, pnl_col)` — 
- `bucket_metrics(df, key, pnl_col)` — 
- `field_missing(df, fields)` — 
- `top_rows(df, n)` — 
- `scanner_contract_audit()` — 
- `main()` — 

## hermes\scripts\v25\v165_v164_outcome_and_direction_audit.py
- `fnum(v, default)` — 
- `bval(v)` — 
- `sym_to_kline_path(symbol)` — 
- `load_bars(symbol)` — 
- `date_key(bar)` — 
- `locate_entry(bars, entry_date)` — 
- `simulate(row, bars)` — 
- `metrics(rows, pnl_key)` — 
- `classify(m)` — 
- `group_table(rows, keys)` — 
- `combo_table(rows, combos)` — 
- `write_csv(path, rows)` — 
- `main()` — 
- `simulate_prepared(row, bars)` — 

## hermes\scripts\v25\v166_v164_slice_variant_search.py
- `fnum(v, default)` — 
- `bval(v)` — 
- `date_key(b)` — 
- `kline_path(symbol)` — 
- `load_bars(symbol)` — 
- `locate(bars, entry_date)` — 
- `metrics(rows)` — 
- `classify(m)` — 
- `simulate(row, bars, r_mult, max_hold, sl_buf)` — 
- `write_csv(path, rows)` — 
- `main()` — 

## hermes\scripts\v25\v167_exact_scanner_dry_run.py
- `fnum(v, default)` — 
- `bval(v)` — 
- `rule_pass(r)` — 
- `missing_counts(rows)` — 
- `write_csv(path, rows)` — 
- `read_csv(path)` — 
- `main()` — 

## hermes\scripts\v25\v169_apply_v167_production_candidate.py
- `fnum(v, default)` — 
- `ikey(v)` — 
- `bval(v)` — 
- `read_csv(path)` — 
- `metrics(rows)` — 
- `bucket(rows, key, prefix)` — 
- `convert_trade(row)` — 
- `convert_pick(row)` — 
- `main()` — 

## hermes\scripts\v25\v170_v167_live_degradation_audit.py
- `fnum(v, default)` — 
- `dkey(v)` — 
- `bucket_value(row, key)` — 
- `summarize(rows)` — 
- `group(rows, key)` — 
- `main()` — 
- `pct(k)` — 

## hermes\scripts\v25\v171_v167_frontend_contract_live_guard.py
- `fnum(v, default)` — 
- `dkey(v)` — 
- `load_json(path, default)` — 
- `write_json(path, obj)` — 
- `write_csv(path, rows)` — 
- `backup(path, stamp)` — 
- `sym_key(symbol)` — 
- `last_cached_bar(symbol)` — 
- `normalize_core(row)` — 
- `enrich_rows(rows, dna)` — 
- `field_missing(rows)` — 
- `metrics(rows)` — 
- `monthly_stats(trades)` — 
- `replay_rows(trades)` — 
- `guard_active_picks(picks)` — 
- `main()` — 

## hermes\scripts\v25\v172_v167_high_quality_gate.py
- `fnum(v, default)` — 
- `dkey(v)` — 
- `load(path, default)` — 
- `dump(path, obj)` — 
- `gate(r)` — 
- `metrics(rows)` — 
- `field_missing(rows)` — 
- `classify(m)` — 
- `enrich_version(r, scope)` — 
- `main()` — 

## hermes\scripts\v25\v173_v172_next_quality_frontier.py
- `fnum(v, default)` — 
- `dkey(v)` — 
- `load_json(path, default)` — 
- `v172_gate(r)` — 
- `metrics(rows)` — 
- `classify(m)` — 
- `make_conditions()` — 
- `write_csv(path, rows)` — 
- `main()` — 
- `add(name, pred)` — 
- `selected_pass(r)` — 

## hermes\scripts\v25\v174_v172_wave_structure_hierarchy_audit.py
- `f(v, default)` — 
- `dkey(v)` — 
- `bdate(b)` — 
- `kline_path(symbol)` — 
- `load_bars(symbol, cache)` — 
- `locate(bars, date)` — 
- `atr(bars, idx, n)` — 
- `pivots(bars, left, right, kind, upto)` — 
- `audit_one(row, cache)` — 
- `metrics(rows)` — 
- `write_csv(path, rows)` — 
- `main()` — 

## hermes\scripts\v25\v175_semantic_split_materialize.py
- `f(v, default)` — 
- `dkey(v)` — 
- `load(path, default)` — 
- `metrics(rows)` — 
- `audit_index()` — 
- `enrich(row, aud, scope)` — 
- `main()` — 

## hermes\scripts\v25\v177_exit_replay_research.py
- `as_float(x, default)` — 
- `date_of(b)` — 
- `norm_bar(b)` — 
- `load_bars(symbol)` — 
- `pnl_pct(price, entry)` — 
- `metrics(rows)` — 
- `gate(m)` — 
- `simulate(t, bars, variant)` — 
- `main()` — 

## hermes\scripts\v25\v178_time_path_attribution.py
- `f(x, default)` — 
- `date_of(b)` — 
- `norm_bar(b)` — 
- `load_bars(symbol, suffix)` — 
- `pnl_pct(px, entry)` — 
- `find_idx(bars, date, fallback)` — 
- `classify(row)` — 
- `summarize(rows, key)` — 
- `main()` — 

## hermes\scripts\v25\v179_time_intraday_probe.py
- `f(x, default)` — 
- `market_code(symbol)` — 
- `cache_path(symbol)` — 
- `fetch_60(symbol)` — 
- `load_60(symbol)` — 
- `classify_60(row)` — 
- `main()` — 
- `group(key)` — 

## hermes\scripts\v25\v180_research_direction_closure.py
- `load(p)` — 
- `pick_metric(d)` — 

## hermes\scripts\v25\v185_daily_rematerialize.py
- `load(path, default)` — 
- `dkey(v)` — 
- `fnum(v, default)` — 
- `kline_path(symbol)` — 
- `load_symbol_bars(symbol)` — 
- `active_lifecycle_fields(row)` — Materialize non-outcome execution contract fields for active picks.
- `replay_active_exit(row)` — Replay one active row under the executable V185 contract.
- `latest_market_date_for_rows(rows)` — 
- `latest_global_kline_date()` — 
- `write_json(path, data)` — 
- `write_csv(path, rows)` — 
- `normalize_active_row(row)` — 
- `metrics(trades)` — 
- `fail_closed_if_causality_rejected()` — 
- `main()` — 

## hermes\scripts\v25\v231_daily_current_shadow_audit.py
- `sf(x, default)` — 
- `dn(x)` — 
- `row_key(r)` — 
- `load_json(path, default)` — 
- `latest_path(pattern)` — 
- `latest_v164_dryrun()` — 
- `latest_v231_combined_csv()` — 
- `sym_from_file(path)` — 
- `build_all_market_strong1()` — 
- `previous_market_date(dates, entry_date)` — 
- `load_history_keys()` — 
- `selector_leak_fields(fields)` — 
- `main()` — 

## hermes\scripts\v25\v236_daily_current_shadow_audit.py
- `sf(x, default)` — 
- `dn(x)` — 
- `row_key(r)` — 
- `load_json(path, default)` — 
- `latest_path(pattern)` — 
- `latest_v164_dryrun()` — 
- `latest_v231_combined_csv()` — 
- `sym_from_file(path)` — 
- `build_all_market_strong1()` — 
- `load_breadth_above_ma20()` — 
- `previous_market_date(dates, entry_date)` — 
- `load_history_keys()` — 
- `selector_leak_fields(fields)` — 
- `rule_pass(r)` — 
- `main()` — 

## hermes\scripts\v25\v244_industry_probe.py
- `dn(x)` — 
- `sf(x, default)` — 
- `metrics(df)` — 
- `pass_gate(m, gate)` — 
- `prev_date(d)` — 
- `attach_ind(df)` — 

## hermes\scripts\v25\v245_source_field_separator_probe.py
- `dn(x)` — 
- `metrics(df)` — 
- `ok(m, g)` — 

## hermes\scripts\v25\v246_daily_current_shadow_audit.py
- `sf(x, default)` — 
- `dn(x)` — 
- `row_key(r)` — 
- `load_json(path, default)` — 
- `latest_path(pattern)` — 
- `latest_v164_dryrun()` — 
- `sym_from_file(path)` — 
- `previous_market_date(dates, entry_date)` — 
- `build_all_market_strong1()` — 
- `load_breadth_above_ma20()` — 
- `build_industry_features()` — 
- `latest_history_csv(pattern)` — 
- `load_history_keys()` — 
- `selector_leak_fields(fields)` — 
- `parent_rule_pass(r)` — 
- `v246_rule_pass(r)` — 
- `main()` — 

## hermes\scripts\v25\v246_industry_addback_candidate.py
- `dn(x)` — 
- `metrics(df)` — 
- `pass_gate(m, g)` — 

## hermes\scripts\v25\v247_v246_current_smoke.py

## hermes\scripts\v25\v248_v246_independent_audit.py
- `dn(x)` — 
- `sf(x, default)` — 
- `metrics(df)` — 
- `pass_gate(m, gate)` — 
- `stable_hash(df)` — 
- `period_metrics(df, period)` — 
- `rolling_metrics(df, window)` — 

## hermes\scripts\v25\v256_preentry_weekly_structure_probe.py
- `sym_to_path(sym)` — 
- `load_bars(sym)` — 
- `pct(a, b)` — 
- `max_drawup(prior, n)` — 
- `compute_feature(row)` — 
- `metrics(df)` — 
- `pass_gate(m, gate)` — 
- `enrich(df)` — 
- `search_rules(df)` — 
- `current_coverage()` — 
- `main()` — 

## hermes\scripts\v25\v258_current_compatible_rich_source_mining.py
- `norm_date(s)` — 
- `add_key(df)` — 
- `metrics(df)` — 
- `pass_gate(m, gate)` — 
- `pred_mask(df, pred)` — 
- `pred_str(pred)` — 
- `build_predicates(hist_child, current)` — 
- `main()` — 

## hermes\scripts\v25\v259_bos_continuation_source_safe_rebuild.py
- `norm_date(s)` — 
- `add_key(df)` — 
- `metrics(df)` — 
- `pass_gate(m, gate)` — 
- `kline_path(symbol)` — 
- `index_by_date(rows, date_s)` — 
- `raw_features(row, cache)` — 
- `pred_mask(df, pred)` — 
- `pred_str(pred)` — 
- `build_preds(df)` — 
- `main()` — 

## hermes\scripts\v25\v261_current_supply_mismatch_closure.py
- `load_v259_module()` — 
- `safe_value_counts(df, col)` — 
- `add_raw_features_to_current(df)` — 
- `current_selector_mismatch(cur)` — 
- `frontier_current_hit_audit(frontier)` — 
- `main()` — 

## hermes\scripts\v25\v262_fresh_bos_retest_generator.py
- `fnum(x, default)` — 
- `date_s(bar)` — 
- `symbol_from_path(path)` — 
- `add_key(df)` — 
- `metrics(df)` — 
- `pass_gate(m, gate)` — 
- `replay_exit(bars, entry_idx, entry, sl, rr, max_hold)` — 
- `scan_symbol(path)` — 
- `quantile_thresholds(s, qs, decimals)` — 
- `apply_rule(df, rule)` — 
- `rule_text(rule)` — 
- `main()` — 

## hermes\scripts\v25\v263_v262_60m_confirmation_probe.py
- `add_key(df)` — 
- `metrics(df)` — 
- `pass_gate(m, gate)` — 
- `fnum(x, default)` — 
- `sym_stem(symbol)` — 
- `m60_path(symbol)` — 
- `add_m60_features(df)` — 
- `main()` — 
- `mask(df, preds)` — 

## hermes\scripts\v25\v264_liquidity_sweep_reclaim_source_probe.py
- `fnum(x, default)` — 
- `date_s(bar)` — 
- `symbol_from_path(path)` — 
- `add_key(df)` — 
- `metrics(df)` — 
- `pass_gate(m, gate)` — 
- `replay_exit(bars, entry_idx, entry, sl, rr, max_hold)` — 
- `generate_symbol(path)` — 
- `cut_recent(df)` — 
- `quantile_thresholds(s, qs)` — 
- `main()` — 

## hermes\scripts\v25\v265_breakout_retest_reclaimed_support_probe.py
- `fnum(x, default)` — 
- `date_s(bar)` — 
- `symbol_from_path(path)` — 
- `add_key(df)` — 
- `metrics(df)` — 
- `pass_gate(m, gate)` — 
- `replay_exit(bars, entry_idx, entry, sl, rr, max_hold)` — 
- `scan_symbol(path)` — 
- `cut_recent(df)` — 
- `qths(s, qs)` — 
- `main()` — 

## hermes\scripts\v25\v267_industry_rotation_retest_source_probe.py
- `fnum(x, default)` — 
- `symbol_from_path(path)` — 
- `add_key(df)` — 
- `load_industry_map()` — 
- `metrics(df)` — 
- `pass_gate(m, gate)` — 
- `load_symbol_bars(industry_map)` — 
- `build_industry_features(symbol_bars, industry_map)` — 
- `simulate_exit(bars, entry_idx, entry_price, sl, tp, max_hold)` — 
- `generate_candidates(symbol_bars, industry_map, ind_feats)` — 
- `apply_preds(df, preds)` — 
- `frontier_search(child, base)` — 
- `main()` — 

## hermes\scripts\v25\v268_eastmoney_board_rotation_retest_source_probe.py
- `load_board_maps()` — 
- `load_all_bars(sym_boards)` — 
- `build_board_features(symbol_bars, sym_boards, boards)` — 
- `best_board_feature(sym, date, sym_boards, feats)` — 
- `generate(symbol_bars, sym_boards, feats)` — 
- `mask(df, preds)` — 
- `frontier(child, base)` — 
- `main()` — 

## hermes\scripts\v25\v269_v262_60m_confirmation_corrected_cache_probe.py
- `add_key(df)` — 
- `metrics(df)` — 
- `pass_gate(m, gate)` — 
- `fnum(x, default)` — 
- `sym_stem(symbol)` — 
- `m60_path(symbol)` — 
- `add_m60_features(df)` — 
- `main()` — 
- `mask(df, preds)` — 

## hermes\scripts\v25\v271_time_order_parameter_surface_probe.py
- `fnum(x, default)` — 
- `date_s(bar)` — 
- `symbol_from_path(path)` — 
- `add_key(df)` — 
- `metrics(df)` — 
- `pass_gate(m, gate)` — 
- `replay_exit(bars, entry_idx, entry, sl, rr, max_hold)` — 
- `has_prior_ssl(bars, event_idx, window, ssl_lb)` — 
- `reclaim_ok(mode, rb, dz_low, dz_high)` — 
- `scan_symbol(path)` — 
- `main()` — 

## hermes\scripts\v25\v272_time_order_parameter_surface_fast.py
- 类: Agg
- `fnum(x, d)` — 
- `date_s(b)` — 
- `symbol_from_path(p)` — 
- `pass_gate(m, g)` — 
- `replay(bars, entry_i, entry, sl)` — 
- `mode_ok(mode, b, zl, zh)` — 
- `prior_ssl_flags(bars, event_i)` — 
- `scan(path, sym_idx, aggs, ssl_aggs, funnel, seen)` — 
- `main()` — 
- `add(self, date, pnl, t1)` — 
- `metrics(self)` — 

## hermes\scripts\v25\v273_sequence_stock_dna_probe.py
- `f(x, d)` — 
- `ds(b)` — 
- `sym(p)` — 
- `mode_ok(mode, b, zl, zh)` — 
- `replay(bars, ei, entry, sl)` — 
- `scan_variant(bars, bos_lb, demand_lb, wait, mode)` — 
- `met(vals)` — 
- `main()` — 

## hermes\scripts\v25\v274_walkforward_stock_dna_sequence.py
- `fnum(x, d)` — 
- `date_s(b)` — 
- `symbol_from_path(p)` — 
- `mode_ok(mode, b, zl, zh)` — 
- `replay(bars, entry_i, entry, sl)` — 
- `variant_key(bos, demand, wait, mode)` — 
- `scan_symbol(path)` — 
- `metrics(rows)` — 
- `train_stats(rows, eval_year)` — 
- `selected_variants(rows, eval_year, grid)` — 
- `walk_forward(rows, grid)` — 
- `main()` — 

## hermes\scripts\v25\v275_temporal_sequence_signature_audit.py
- `fnum(x, d)` — 
- `date_s(b)` — 
- `path_for_symbol(symbol)` — 
- `load_bars(symbol, cache)` — 
- `find_last_ssl(bars, event_i, win)` — Last source-safe SSL sweep before event: low pierces prior20 low and close reclaims it.
- `bkt_num(x, cuts, labels)` — 
- `metrics(df)` — 
- `main()` — 

## hermes\scripts\v25\v276_sequence_supply_chain_attrition.py
- `fnum(x, d)` — 
- `ds(b)` — 
- `symbol_from_path(p)` — 
- `mode_ok(mode, b, zl, zh)` — 
- `replay_exit(bars, entry_i, entry, sl, rr, max_hold)` — 
- `metrics(df)` — 
- `scan_symbol(path)` — 
- `describe_series(s)` — 
- `main()` — 

## hermes\scripts\v25\v277_sequence_supply_chain_attrition_fast.py
- `f(x, d)` — 
- `ds(b)` — 
- `sym(p)` — 
- `mode_ok(mode, b, zl, zh)` — 
- `replay(bars, ei, entry, sl, rr, max_hold)` — 
- `blank()` — 
- `add(acc, pnl, year, symbol, t1)` — 
- `met(acc)` — 
- `scan_one(path)` — 
- `main()` — 
- `desc(col)` — 
- `q(p)` — 

## hermes\scripts\v25\v278_sequence_combo_attrition_ultrafast.py
- `f(x, d)` — 
- `ds(b)` — 
- `sym(p)` — 
- `okmode(m, b, zl, zh)` — 
- `replay(bars, ei, entry, sl)` — 
- `blank()` — 
- `add(a, pnl, year, t1, reason)` — 
- `met(a, stock_count)` — 
- `scan(path)` — 
- `main()` — 
- `desc(col)` — 
- `q(p)` — 

## hermes\scripts\v25\v279_adaptive_temporal_grammar_audit.py
- `f(x, d)` — 
- `ds(b)` — 
- `symbol_from_path(p)` — 
- `blank()` — 
- `add(a, pnl, year, reason, t1)` — 
- `metrics(a, stock_count)` — 
- `replay(bars, entry_i, entry, sl, rr, hold)` — 
- `pct_rank(vals, idx, lb)` — 
- `scan(path)` — 
- `bucket(v, cuts)` — 
- `main()` — 
- `q(p)` — 

## hermes\scripts\v25\v280_layered_state_grammar_audit.py
- `f(x, d)` — 
- `ds(b)` — 
- `symbol_from_path(p)` — 
- `blank()` — 
- `add(a, row)` — 
- `metrics(a, stock_count)` — 
- `bucket(v, cuts)` — 
- `replay(bars, entry_i, entry, sl, rr, hold)` — 
- `quantile(xs, p, default)` — 
- `scan(path)` — 
- `main()` — 
- `emit(i, entry_i, zl, zh, family, regime)` — 

## hermes\scripts\v25\v282_industry_participation_sequence_audit.py
- `sf(x, default)` — 
- `dn(x)` — 
- `symbol_from_path(p)` — 
- `blank()` — 
- `add(a, r)` — 
- `metrics(a)` — 
- `bucket_up(x)` — 
- `bucket_ret(x)` — 
- `bucket_rel(x)` — 
- `load_industry_map()` — 
- `build_prev_features(sym_ind)` — 
- `main()` — 
- `prev_date(d)` — 
- `select_best(xs, min_n, min_year_n)` — 

## hermes\scripts\v25\v283_60min_reaction_overlay_audit.py
- `sf(x, d)` — 
- `dn(x)` — 
- `sym_from_name(p)` — 
- `blank()` — 
- `add(a, r)` — 
- `metrics(a)` — 
- `bret(x)` — 
- `bpos(x)` — 
- `byn(x)` — 
- `prev60_date(sym, entry)` — 

## hermes\scripts\v25\v284_60min_smc_sequence_audit.py
- `sf(x, d)` — 
- `dn(x)` — 
- `sym_from_name(p)` — 
- `blank()` — 
- `add(a, r)` — 
- `metrics(a)` — 
- `bucket_risk(x)` — 
- `bucket_range(x)` — 
- `load_60m()` — 
- `prev_date(dates_by_sym, sym, entry)` — 
- `seq_features(bs, zone_low, zone_high)` — Detect same-day 60m sequence relative to daily demand zone.
- `main()` — 

## hermes\scripts\v25\v285_v280_stock_dna_walkforward.py
- `sf(x, d)` — 
- `bucket_risk(x)` — 
- `bucket_liq(x)` — 
- `bucket_delay(x)` — 
- `bucket_range(x)` — 
- `bucket_vol_ratio(x)` — 
- `blank()` — 
- `add(a, row)` — 
- `metrics(a, stock_count)` — 
- `row_keys(r)` — 
- `main()` — 
- `fit_candidates(test_year, grid, per_symbol)` — 
- `q(p)` — 

## hermes\scripts\v25\v286_parent_regime_selector_walkforward.py
- `sf(x, d)` — 
- `dn(x)` — 
- `symbol_from_path(p)` — 
- `bucket_ret(x)` — 
- `bucket_up(x)` — 
- `bucket_rel(x)` — 
- `bucket_risk(x)` — 
- `bucket_liq(x)` — 
- `bucket_delay(x)` — 
- `bucket_range(x)` — 
- `bucket_vol_ratio(x)` — 
- `blank()` — 
- `add(a, r)` — 
- `merge(dst, src)` — 
- `metrics(a, stock_count)` — 
- `row_rule_keys(r)` — 
- `state_keys(r)` — 
- `load_industry_map()` — 
- `build_prev_features(sym_ind)` — 
- `load_rows()` — 
- `main()` — 
- `prev_date(d)` — 
- `fit(test_year, grid)` — 

## hermes\scripts\v25\v286_parent_regime_walkforward_audit.py
- `sf(x, d)` — 
- `dn(x)` — 
- `symbol_from_path(p)` — 
- `load_industry_map()` — 
- `build_prev_features(sym_ind)` — 
- `b_ret(x)` — 
- `b_up(x)` — 
- `b_rel(x)` — 
- `b_risk(x)` — 
- `b_liq(x)` — 
- `b_rng(x)` — 
- `blank()` — 
- `add(a, r)` — 
- `merge(dst, src)` — 
- `metrics(a)` — 
- `enrich_rows()` — 
- `row_keys(r)` — 
- `main()` — 
- `prev_date(d)` — 
- `train_rules(test_year, grid)` — 

## hermes\scripts\v25\v286_parent_regime_walkforward_selector.py
- `sf(x, d)` — 
- `dn(x)` — 
- `symbol_from_path(p)` — 
- `blank()` — 
- `add(a, r)` — 
- `merge(dst, src)` — 
- `metrics(a, stock_count)` — 
- `bucket_ret(x)` — 
- `bucket_up(x)` — 
- `bucket_rel(x)` — 
- `bucket_risk(x)` — 
- `bucket_liq(x)` — 
- `bucket_range(x)` — 
- `bucket_delay(x)` — 
- `load_industry_map()` — 
- `build_prev_features(sym_ind)` — 
- `enrich_rows()` — 
- `parent_states(r)` — 
- `child_keys(r)` — 
- `row_keys(r)` — 
- `main()` — 
- `prev_date(d)` — 
- `train_global_keys(test_year, grid)` — 
- `train_parent_best_child(test_year, grid)` — 

## hermes\scripts\v25\v286_regime_parent_router_walkforward.py
- `sf(x, d)` — 
- `dn(x)` — 
- `symbol_from_path(p)` — 
- `bucket_ret(x)` — 
- `bucket_up(x)` — 
- `bucket_rel(x)` — 
- `bucket_risk(x)` — 
- `bucket_liq(x)` — 
- `bucket_range(x)` — 
- `bucket_delay(x)` — 
- `blank()` — 
- `add(a, r)` — 
- `merge(dst, src)` — 
- `metrics(a)` — 
- `load_industry_map()` — 
- `build_prev_features(sym_ind)` — 
- `enrich_rows()` — 
- `row_keys(r)` — 
- `main()` — 
- `prev_date(d)` — 
- `fit_rules(test_year, grid)` — 

## hermes\scripts\v25\v286_rolling_period_stock_dna_audit.py
- `sf(x, d)` — 
- `parse_date(s)` — 
- `ym(dt)` — 
- `next_month(dt)` — 
- `bucket_risk(x)` — 
- `bucket_liq(x)` — 
- `bucket_delay(x)` — 
- `bucket_range(x)` — 
- `bucket_vol_ratio(x)` — 
- `row_keys(r)` — 
- `blank()` — 
- `add(a, r)` — 
- `metrics(a, stock_count)` — 
- `train_stat(rows, start, end, per_symbol)` — 
- `fit_from_stats(stats, grid, per_symbol)` — 
- `main()` — 

## hermes\scripts\v25\v286_walkforward_regime_router_audit.py
- `sf(x, d)` — 
- `dn(x)` — 
- `symbol_from_path(p)` — 
- `blank()` — 
- `merge(dst, src)` — 
- `add(a, r)` — 
- `metrics(a, stock_count)` — 
- `bucket_ret(x)` — 
- `bucket_up(x)` — 
- `bucket_rel(x)` — 
- `bucket_risk(x)` — 
- `bucket_liq(x)` — 
- `bucket_delay(x)` — 
- `bucket_range(x)` — 
- `bucket_volr(x)` — 
- `load_industry_map()` — 
- `build_prev_features(sym_ind)` — 
- `row_keys(r)` — 
- `main()` — 
- `prev_date(d)` — 
- `train_rules(test_year, grid)` — 

## hermes\scripts\v25\v287_60min_first_smc_generator.py
- `sf(x, d)` — 
- `dn(x)` — 
- `sym_from_60(p)` — 
- `daily_path(sym)` — 
- `blank()` — 
- `add(a, r)` — 
- `metrics(a, stock_count)` — 
- `load_json(p)` — 
- `replay_daily(daily, signal_date, entry_price_hint, sl, rr, max_hold)` — 
- `day_regime(daily, date)` — 
- `generate_for_symbol(sym, bars60, daily)` — 
- `main()` — 

## hermes\scripts\v25\v287_event_time_rolling_regime_router.py
- `parse_dt(s)` — 
- `sub(a, r)` — Inverse of v286.add for rolling-window aggregates.
- `passes(m, grid)` — 
- `main()` — 

## hermes\scripts\v25\v287_regime_conditioned_rolling_selector.py
- `sf(x, d)` — 
- `dn(x)` — 
- `parse_date(s)` — 
- `ym(dt)` — 
- `next_month(dt)` — 
- `symbol_from_path(p)` — 
- `bucket_ret(x)` — 
- `bucket_up(x)` — 
- `bucket_rel(x)` — 
- `bucket_risk(x)` — 
- `bucket_liq(x)` — 
- `bucket_delay(x)` — 
- `bucket_range(x)` — 
- `load_industry_map()` — 
- `build_prev_features(sym_ind)` — 
- `blank()` — 
- `add(a, r)` — 
- `metrics(a, stock_count)` — 
- `row_keys(r)` — 
- `train_stats(rows, start, end)` — 
- `fit_rules(stats, grid)` — 
- `loss_decomp(rows, limit)` — 
- `main()` — 
- `prev_date(d)` — 

## hermes\scripts\v25\v287_same_source_60m_generator_audit.py
- `sf(x, d)` — 
- `dn(x)` — 
- `symbol_from_60(p)` — 
- `day_path(sym)` — 
- `load_daily(sym)` — 
- `load_60_file(p)` — 
- `blank()` — 
- `add(a, r)` — 
- `metrics(a, stock_count)` — 
- `replay_daily(daily, entry_idx, entry, sl, tp, max_hold)` — 
- `daily_state(daily, idx)` — 
- `risk_bucket(x)` — 
- `relvol_bucket(x)` — 
- `generate_for_symbol(sym, bars60, daily)` — 
- `main()` — 

## hermes\scripts\v25\v287_strong_participation_upcont_pocket_audit.py
- `sf(x, d)` — 
- `year_month(d)` — 
- `blank()` — 
- `add(a, r)` — 
- `metrics(a)` — 
- `main()` — 
- `strong_mkt_ind(r)` — 
- `euphoric_breadth(r)` — 
- `upcont_down(r)` — 
- `risk8(r)` — 
- `rng25(r)` — 
- `highvol(r)` — 
- `rel_0_10(r)` — 

## hermes\scripts\v25\v288_rolling_regime_window_audit.py
- `sf(x, d)` — 
- `blank()` — 
- `add(a, r)` — 
- `metrics(a)` — 
- `load_industry_map()` — 
- `build_daily_ret_tables(sym_ind)` — 
- `mean(xs)` — 
- `enrich_rows()` — 
- `main()` — 
- `base(r)` — 
- `risk8(r)` — 

## hermes\scripts\v25\v288_same_source_60m_first_generator.py
- `sf(x, d)` — 
- `dn(x)` — 
- `sym_from_60(p)` — 
- `sym_to_day_path(sym)` — 
- `load_daily(sym)` — 
- `next_daily_index(daily, signal_day)` — 
- `replay_daily(daily, entry_i, entry, sl, rr, max_hold)` — 
- `blank()` — 
- `add(a, r)` — 
- `metrics(a, stock_count)` — 
- `find_60m_files()` — 
- `detect_events(sym, bars60, daily)` — 
- `bucket(x, cuts, labels)` — 
- `main()` — 

## hermes\scripts\v25\v289_60m_first_participation_overlay.py
- `sf(x, d)` — 
- `dn(x)` — 
- `sym_from_path(p)` — 
- `bret(x)` — 
- `bup(x)` — 
- `brel(x)` — 
- `blank()` — 
- `add(a, r)` — 
- `metrics(a, stock_count)` — 
- `build_prev(sym_ind)` — 
- `main()` — 
- `prev(d)` — 

## hermes\scripts\v25\v290_operator_lifecycle_overlay.py
- `sf(x, d)` — 
- `dn(x)` — 
- `path60(sym)` — 
- `brange(x)` — 
- `bdepth(x)` — 
- `bimp(x)` — 
- `bhold(x)` — 
- `blank()` — 
- `add(a, r)` — 
- `metrics(a, stock_count)` — 
- `enrich(r, cache)` — 
- `main()` — 

## hermes\scripts\v25\v291_intraday_limit_entry_audit.py
- `sf(x, d)` — 
- `dn(x)` — 
- `sym_paths(sym)` — 
- `load60(sym, cache)` — 
- `load_daily(sym, cache)` — 
- `replay_daily(daily, entry_date, entry, sl, rr, max_hold)` — 
- `target_price(r, mode)` — 
- `fill_intraday(row, mode, bars60, max_bars)` — 
- `blank()` — 
- `add(a, r)` — 
- `metrics(a, stock_count, source_n)` — 
- `bucket(x, cuts, labels)` — 
- `main()` — 

## hermes\scripts\v25\v292_next_session_60m_confirmation_audit.py
- `sf(x, d)` — 
- `dn(x)` — 
- `paths(sym)` — 
- `load60(sym, cache)` — 
- `loadday(sym, cache)` — 
- `replay(daily, entry_date, entry, sl, rr, max_hold)` — 
- `blank()` — 
- `add(a, r)` — 
- `metrics(a, stock_count, source_n)` — 
- `confirm(row, bars, mode)` — 
- `bucket(x, cuts, labels)` — 
- `main()` — 

## hermes\scripts\v25\v293_entry60_participation_lifecycle_audit.py
- `sf(x, d)` — 
- `dn(x)` — 
- `symbol_from_path(p)` — 
- `path60(sym)` — 
- `brange(x)` — 
- `bdepth(x)` — 
- `bimp(x)` — 
- `bret(x)` — 
- `bup(x)` — 
- `brel(x)` — 
- `bconfirm(x)` — 
- `bvol(x)` — 
- `blank()` — 
- `add(a, r)` — 
- `metrics(a, stock_count, source_n)` — 
- `load_bars(sym, cache)` — 
- `build_entry60_context(sym_ind)` — 
- `lifecycle(row, bars)` — 
- `main()` — 

## hermes\scripts\v25\v294_entry60_persistence_audit.py
- `sf(x, d)` — 
- `dn(x)` — 
- `symbol_from_path(p)` — 
- `path60(sym)` — 
- `pathday(sym)` — 
- `load_json(p)` — 
- `load60(sym, cache)` — 
- `loadday(sym, cache)` — 
- `daybars(bars, d)` — 
- `replay(daily, entry_date, entry, sl, rr, max_hold)` — 
- `blank()` — 
- `add(a, r)` — 
- `metrics(a, stock_count, source_n)` — 
- `bup(x)` — 
- `bdecay(x)` — 
- `bret(x)` — 
- `build_k_context(sym_ind, ks)` — 
- `simulate(rows, sym_ind, stock_ctx, mctx, ictx)` — 
- `main()` — 

## hermes\scripts\v25\v295_v294_weak_month_root_cause.py
- `sf(x, d)` — 
- `blank()` — 
- `add(a, r)` — 
- `metrics(rows)` — 
- `q(vals, p)` — 
- `profile(rows)` — 
- `group(rows, field, min_n)` — 
- `pass_rule(r, rule)` — 
- `rule_label(rule)` — 
- `search_rules(rows)` — 
- `main()` — 

## hermes\scripts\v25\v296_second60_antichase_lifecycle_gate.py
- `load_v294()` — 
- `sf(x, d)` — 
- `blank()` — 
- `add(a, r)` — 
- `metrics(rows, source_n)` — 
- `bad_lifecycle_shallow_weak(r)` — 
- `bad_lifecycle_wide_shallow(r)` — 
- `make_gates()` — 
- `simulate_persistence(source, core, sym_ind, stock_ctx, mctx, ictx)` — 
- `score_rules(rows, source_n)` — 
- `group_decomp(rows)` — 
- `main()` — 

## hermes\scripts\v25\v297_intraday_acc_man_dis_generator.py
- `sf(x, d)` — 
- `dn(t)` — 
- `sym_from_path(p)` — 
- `path60(sym)` — 
- `pathday(sym)` — 
- `load_json(p)` — 
- `load60(sym)` — 
- `loadday(sym, cache)` — 
- `next_day_open(daily, signal_date)` — 
- `replay(daily, entry_date, entry, sl, rr, max_hold)` — 
- `bucket(x, cuts, last)` — 
- `scan_symbol(sym, bars, daily)` — 
- `blank()` — 
- `add(a, r)` — 
- `metrics(rows, source_n)` — 
- `bucket_metrics(rows, source_n)` — 
- `score_rules(rows, source_n)` — 
- `main()` — 

## hermes\scripts\v25\v298_v297_entry60_persistence_overlay.py
- `load_v294()` — 
- `main()` — 

## hermes\scripts\v25\v299_strict_60m_lifecycle_gate.py
- `load_core()` — 
- `mean(xs)` — 
- `pct(a, b)` — 
- `bucket(x, cuts, last)` — 
- `scan_symbol(sym, bars, daily)` — 
- `metrics(rows, source_n)` — 
- `score_rules(rows)` — 
- `bucket_metrics(rows)` — 
- `weak_month_autopsy(rows, rule_rows)` — 
- `main()` — 
- `sf(x, d)` — 
- `sf(x, d)` — 

## hermes\scripts\v25\v300_entry60_volume_diffusion_audit.py
- `load_core()` — 
- `sf(x, d)` — 
- `dn(x)` — 
- `load_source()` — 
- `mean(xs)` — 
- `bret(x)` — 
- `bvol(x)` — 
- `build_volume_context(sym_ind, ks)` — 
- `enrich_rows(source, sym_ind, stock_ctx, mctx, ictx)` — 
- `metric_rows(rows, stock_count, source_n)` — 
- `evaluate(enriched, stock_count, source_n)` — 
- `decompose(rows, stock_count, source_n)` — 
- `main()` — 

## hermes\scripts\v25\v301_prevday_board_leadership_overlay.py
- `load_core()` — 
- `sf(x, d)` — 
- `dn(x)` — 
- `read_rows(path)` — 
- `write_rows(path, rows)` — 
- `metric(rows, stock_count, source_n)` — 
- `daily_symbol_from_path(p)` — 
- `build_board_context(sym_ind)` — Return market and industry board context by trading date.
- `enrich(rows, sym_ind, mctx, ictx, prev_map)` — 
- `v300_base_two_year(r)` — 
- `evaluate(rows, stock_count, source_n)` — 
- `decompose(rows, stock_count, source_n)` — 
- `main()` — 

## hermes\scripts\v25\v302_15m_same_source_lifecycle_audit.py
- `sf(x, d)` — 
- `dn(x)` — 
- `symbol_from_daily_path(p)` — 
- `tencent_code(sym)` — 
- `cache15_path(sym)` — 
- `day_path(sym)` — 
- `load_json(p)` — 
- `normalize_m15(raw, sym)` — 
- `fetch_one(sym)` — 
- `load15(sym)` — 
- `loadday(sym, cache)` — 
- `next_day_open(daily, signal_date)` — 
- `replay(daily, entry_date, entry, sl, rr, max_hold)` — 
- `bucket(x, cuts, last)` — 
- `scan_symbol(sym, bars, daily)` — 
- `blank()` — 
- `add(a, r)` — 
- `finalize(a)` — 
- `metrics(rows)` — 
- `top_variants(rows)` — 
- `main()` — 

## hermes\scripts\v25\v303_executable_15m_entry_timing_audit.py
- `sf(x, d)` — 
- `dn(x)` — 
- `load_json(p)` — 
- `day_path(sym)` — 
- `cache15_path(sym)` — 
- `loadday(sym, cache)` — 
- `load15(sym, cache)` — 
- `bars_on_date(bars, date)` — 
- `replay_t1_daily(daily, entry_date, entry, sl, rr, max_hold)` — 
- `bucket(x, cuts, last)` — 
- `entry_candidates(row, day15, day_open)` — 
- `blank()` — 
- `add(a, r)` — 
- `finalize(a)` — 
- `metrics(rows)` — 
- `top_variants(rows)` — 
- `main()` — 
- `add_mode(mode, price, bar_no, ok, obs_low, obs_high)` — 

## hermes\scripts\v25\v304_entry15_market_industry_diffusion_audit.py
- `sf(x, d)` — 
- `dn(x)` — 
- `load_json(p)` — 
- `sym_from_15_path(p)` — 
- `load_industry_map()` — 
- `day_groups(bars)` — 
- `symbol_day_features(p, need_dates)` — 
- `bucket(x, cuts, last)` — 
- `b_up(x)` — 
- `b_ret(x)` — 
- `b_vr(x)` — 
- `b_rel(x)` — 
- `blank()` — 
- `add(a, r)` — 
- `finalize(a)` — 
- `metrics(rows)` — 
- `top_variants(rows)` — 
- `main()` — 
- `agg_features(sym, d, cut)` — 

## hermes\scripts\v25\v305_morning15_persistence_audit.py
- `sf(x, d)` — 
- `dn(x)` — 
- `load_json(p)` — 
- `day_path(sym)` — 
- `cache15_path(sym)` — 
- `sym_from_15_path(p)` — 
- `load_industry_map()` — 
- `load_day(sym, cache)` — 
- `load15(sym, cache)` — 
- `day_groups(bars)` — 
- `bars_on_date(bars, date)` — 
- `replay_t1_daily(daily, entry_date, entry, sl, rr, max_hold)` — 
- `bucket(x, cuts, last)` — 
- `b_up(x)` — 
- `b_ret(x)` — 
- `b_vr(x)` — 
- `b_rel(x)` — 
- `b_risk(x)` — 
- `b_gap(x)` — 
- `symbol_morning_features(p, need_dates)` — 
- `build_market_features(need_dates, industry_map)` — 
- `entry_candidates(row, day15, day_open)` — 
- `blank()` — 
- `add(a, r)` — 
- `finalize(a)` — 
- `metrics(rows)` — 
- `top_variants(rows)` — 
- `main()` — 
- `span(k)` — 
- `add_mode(mode, horizon, k, ok, obs_close, obs_low)` — 
- `feat(k)` — 

## hermes\scripts\v25\v306_opening_gap_source_audit.py
- `sf(x, d)` — 
- `load_json(p)` — 
- `dn(x)` — 
- `load_industry_map()` — 
- `sym_from_day_path(p)` — 
- `daily_paths()` — 
- `bucket(x, cuts, last)` — 
- `b_gap(x)` — 
- `b_up(x)` — 
- `b_rel(x)` — 
- `b_rank(x)` — 
- `build_gap_features(needed_dates, industry)` — 
- `blank()` — 
- `add(a, r)` — 
- `metrics(a)` — 
- `top_groups(rows, dims, min_n)` — 
- `top_combos(rows, combos, min_n)` — 
- `main()` — 

## hermes\scripts\v25\v307_industry_leadership_transmission_audit.py
- `sf(x, d)` — 
- `dn(x)` — 
- `load_json(p)` — 
- `load_industry_map()` — 
- `sym_from_15_path(p)` — 
- `bucket(x, cuts, last)` — 
- `b_rank(x)` — 
- `b_ret(x)` — 
- `b_up(x)` — 
- `b_amt_rank(x)` — 
- `day_groups(rows)` — 
- `build_leadership(needed_dates, industry)` — 
- `blank()` — 
- `add(a, r)` — 
- `metrics(a)` — 
- `top_groups(rows, dims, min_n)` — 
- `top_combos(rows, combos, min_n)` — 
- `main()` — 

## hermes\scripts\v25\v308_daily_industry_leadership_proxy_audit.py
- `sf(x, d)` — 
- `load_json(p)` — 
- `load_industry_map()` — 
- `sym_from_daily_path(p)` — 
- `bucket(x, cuts, last)` — 
- `b_gap(x)` — 
- `b_rank_pct(x)` — 
- `b_up(x)` — 
- `b_risk(x)` — 
- `b_range(x)` — 
- `blank()` — 
- `add(a, r)` — 
- `metrics(a)` — 
- `build_daily_proxy(needed_dates, industry)` — 
- `enrich_rows(rows, stock_feat, ind_feat, industry)` — 
- `aggregate(rows, dims, min_n)` — 
- `main()` — 

## hermes\scripts\v25\v309_scanner_time_intraday_continuation_audit.py
- `sf(x, d)` — 
- `dn(x)` — 
- `load_json(p)` — 
- `load_industry_map()` — 
- `day_path(sym)` — 
- `cache15_path(sym)` — 
- `sym_from_15_path(p)` — 
- `load_day(sym, cache)` — 
- `load15(sym, cache)` — 
- `day_groups(bars)` — 
- `bars_on_date(bars, date)` — 
- `replay_t1_daily(daily, entry_date, entry, sl, rr, max_hold)` — 
- `bucket(x, cuts, last)` — 
- `b_up(x)` — 
- `b_ret(x)` — 
- `b_vr(x)` — 
- `b_rel(x)` — 
- `b_risk(x)` — 
- `b_dd(x)` — 
- `b_push(x)` — 
- `b_rank(x)` — 
- `symbol_intraday_features(p, need_dates)` — 
- `build_features(need_dates, industry_map)` — 
- `entry_variants(row, day15)` — 
- `blank()` — 
- `add(a, r)` — 
- `finalize(a)` — 
- `metrics(rows)` — 
- `top_variants(rows)` — 
- `main()` — 

## hermes\scripts\v25\v310_v309_rule_stability_dedup_audit.py
- `sf(x, d)` — 
- `load_json(path)` — 
- `blank()` — 
- `add(a, r)` — 
- `finalize(a)` — 
- `metrics(rows)` — 
- `row_rule_labels(r)` — 
- `dedup_rows(rows, key_fields)` — 
- `group_by_rule(rows)` — 
- `previous_month_rule_walk(rows)` — 
- `main()` — 

## hermes\scripts\v25\v311_v309_rule_walkforward_failure_attribution.py
- `sf(x, d)` — 
- `load_json(path)` — 
- `blank()` — 
- `add(a, r)` — 
- `metrics(rows)` — 
- `dedup_candidate(rows)` — 
- `labels(r)` — 
- `row_matches_rule(r, rule)` — 
- `build_rule_table(rows)` — 
- `leave_one_month_out(rows, all_rules)` — 
- `weak_month_attribution(rows, month)` — 
- `main()` — 

## hermes\scripts\v25\v312_production_shadow_branch_checkpoint.py
- `load(path, default)` — 
- `dkey(v)` — 
- `fnum(v, default)` — 
- `active_summary(rows)` — 
- `main()` — 

## hermes\scripts\v25\v313_v185_active_pick_lifecycle_audit.py
- `load_json(path, default)` — 
- `dkey(v)` — 
- `fnum(v, default)` — 
- `kline_path(symbol)` — 
- `load_bars(symbol)` — 
- `audit_row(r)` — 
- `main()` — 

## hermes\scripts\v25\v314_v185_active_executable_exit_audit.py
- `load_json(path, default)` — 
- `dkey(v)` — 
- `fnum(v, default)` — 
- `kline_path(symbol)` — 
- `load_bars(symbol)` — 
- `replay_exit(row)` — 
- `main()` — 

## hermes\scripts\v25\v315_v185_preentry_structural_frontier_audit.py
- `fnum(x, default)` — 
- `date_of_bar(b)` — 
- `load_kline(symbol)` — 
- `pct(a, b)` — 
- `close(b)` — 
- `high(b)` — 
- `low(b)` — 
- `open_(b)` — 
- `vol(b)` — 
- `derive_preentry(row)` — 
- `metrics(rows)` — 
- `gate_status(m)` — 
- `cond_rows(rows, feats, conds)` — 
- `main()` — 

## hermes\scripts\v25\v316_v185_exit_mechanism_frontier_audit.py
- `fnum(x, default)` — 
- `dkey(v)` — 
- `load_bars(symbol)` — 
- `t1_path(row)` — 
- `simulate(row, cfg)` — 
- `finish(row, b, reason, price, pnl, hold)` — 
- `metrics(rows)` — 
- `gate(m)` — 
- `baseline_metrics(rows)` — 
- `loss_attribution(rows)` — 
- `main()` — 

## hermes\scripts\v25\v317_v185_dynamic_exit_overlay_audit.py
- `load_mod(name, path)` — 
- `fnum(x, default)` — 
- `dkey(v)` — 
- `materialized_row(r)` — 
- `metrics(rows)` — 
- `cond_ok(fs, conds)` — 
- `run_policy(trades, feats, fast_by_id, conds)` — 
- `parse_rule(rule)` — 
- `main()` — 

## hermes\scripts\v25\v318_v167_candidate_supply_frontier_audit.py
- `load_mod(name, path)` — 
- `fnum(x, default)` — 
- `dkey(v)` — 
- `materialized(r)` — 
- `metrics(rows)` — 
- `cond_ok(fs, conds)` — 
- `parse_rule(rule)` — 
- `selected_indices(feats, conds)` — 
- `main()` — 

## hermes\scripts\v25\v319_m60_entry_feasibility_audit.py
- `f(x, default)` — 
- `dkey(v)` — 
- `load60(sym)` — 
- `pct(a, b)` — 
- `metrics(rows)` — 
- `simulate_limit(row, entry, reason)` — 
- `main()` — 

## hermes\scripts\v25\v319_m60_feasibility_audit.py
- `dkey(v)` — 
- `load60(symbol)` — 
- `audit_dataset(name, path)` — 
- `main()` — 

## hermes\scripts\v25\v320_fast_raw_compression_breakout_retest_generator.py
- `f(x, d)` — 
- `dkey(v)` — 
- `pct(a, b)` — 
- `load_bars(p)` — 
- `sym_from(p)` — 
- `finish(sym, eb, xb, entry, sl, tp)` — 
- `simulate(sym, bars, ei, entry, sl, rr)` — 
- `gen(sym, bars, p)` — 
- `metrics(rows)` — 
- `main()` — 

## hermes\scripts\v25\v320_fresh_supply_vs_v185_audit.py
- `dkey(v)` — 
- `prep_base()` — 
- `metrics(df)` — 
- `pass_gate(m)` — 
- `mask(df, preds)` — 
- `main()` — 

## hermes\scripts\v25\v320_raw_compression_breakout_retest_generator.py
- `f(x, default)` — 
- `dkey(v)` — 
- `pct(a, b)` — 
- `load_bars(p)` — 
- `symbol_from_path(p)` — 
- `simulate(sym, bars, entry_i, entry, sl, rr)` — 
- `finish(sym, eb, xb, entry, sl, tp)` — 
- `gen_signals(sym, bars, param)` — 
- `metrics(rows)` — 
- `main()` — 

## hermes\scripts\v25\v321_fast_raw_ssl_sweep_reclaim_generator.py
- `f(x, d)` — 
- `dkey(v)` — 
- `pct(a, b)` — 
- `load_bars(p)` — 
- `sym_from(p)` — 
- `sim(sym, bars, ei, entry, sl, rr)` — 
- `row(sym, eb, xb, entry, sl, tp)` — 
- `gen(sym, bars, p)` — 
- `metrics(rows)` — 
- `main()` — 

## hermes\scripts\v25\v321_raw_ssl_sweep_reclaim_generator.py
- `f(x, d)` — 
- `dkey(v)` — 
- `pct(a, b)` — 
- `load_bars(p)` — 
- `sym_from(p)` — 
- `finish(sym, eb, xb, entry, sl, tp)` — 
- `simulate(sym, bars, ei, entry, sl, rr)` — 
- `gen(sym, bars, p)` — 
- `metrics(rows)` — 
- `main()` — 

## hermes\scripts\v25\v321_v246_vs_v185_promotion_readiness_audit.py
- `load(path, default)` — 
- `main()` — 

## hermes\scripts\v25\v322_current_scanner_contract_recompute_audit.py
- `load_mod(path, name)` — 
- `dkey(v)` — 
- `sf(v, default)` — 
- `load_json(path, default)` — 
- `kline_dates(symbol)` — 
- `actual_bars_since(symbol, entry_date, latest_market_date)` — 
- `main()` — 
- `c_actual(arr)` — 

## hermes\scripts\v25\v322_market_breadth_overlay_audit.py
- `f(x, d)` — 
- `dkey(v)` — 
- `load_bars(p)` — 
- `metrics(rows)` — 
- `main()` — 
- `prev_breadth(ed)` — 

## hermes\scripts\v25\v323_v322_direct_current_shadow.py
- `sf(x, default)` — 
- `dkey(v)` — 
- `load_json(p, default)` — 
- `load_bars(sym)` — 
- `pct(a, b)` — 
- `replay_status(r)` — 
- `finish(reason, status, b, price, entry, sl)` — 
- `main()` — 

## hermes\scripts\v25\v324_v185_delayed_confirmation_entry_audit.py
- `f(x, default)` — 
- `dkey(v)` — 
- `pct(a, b)` — 
- `kline_path(symbol)` — 
- `load_bars(symbol)` — 
- `find_idx(bars, date_s)` — 
- `finish(src, variant, entry_bar, exit_bar, entry, sl)` — 
- `simulate(src, bars, entry_i, entry, sl, rr)` — 
- `bar_features(row, b, prior_entry, zone_high, sl)` — 
- `metrics(rows)` — 
- `main()` — 

## hermes\scripts\v25\v325_v246_route_promotion_blocker_audit.py
- `dn(x)` — 
- `sf(x, default)` — 
- `metrics(df)` — 
- `pass_gate(m, g)` — 
- `current_strict_parent_equivalent(r)` — 
- `load_json(p, default)` — 
- `main()` — 

## hermes\scripts\v25\v326_v246_lineage_current_supply_audit.py
- `sf(x, default)` — 
- `dn(x)` — 
- `load_json(path, default)` — 
- `sym_from_file(path)` — 
- `kline_dates(symbol)` — 
- `actual_bars_since(symbol, entry_date)` — 
- `row_key(r)` — 
- `build_all_market_strong1()` — 
- `load_breadth_above_ma20()` — 
- `previous(dates, d)` — 
- `build_industry_features()` — 
- `industry_addback_pass(r)` — 
- `boolish(x)` — 
- `line_v161(r)` — 
- `line_v175(r)` — 
- `line_v211(r)` — 
- `line_v246_stale_parent(r)` — 
- `load_history()` — 
- `summarize(rows, hist)` — 
- `main()` — 

## hermes\scripts\v25\v327_v326_current_candidate_executable_replay.py
- `dn(x)` — 
- `sf(x, default)` — 
- `load_json(p, default)` — 
- `bars(symbol)` — 
- `replay(r)` — 
- `main()` — 

## hermes\scripts\v25\v328_current_supply_gap_and_relaxed_gate_audit.py
- `load_mod(path, name)` — 
- `dn(x)` — 
- `sf(x, default)` — 
- `boolish(x)` — 
- `load_json(p, default)` — 
- `bars(sym)` — 
- `actual_bars_since(sym, ed)` — 
- `replay(r)` — 
- `metrics(rows)` — 
- `pass_gate(m)` — 
- `main()` — 
- `industry(r)` — 
- `base_quality(r)` — 

## hermes\scripts\v25\v330_v327_current_open_quality_slice_audit.py
- `sf(x, default)` — 
- `dn(x)` — 
- `boolish(x)` — 
- `metrics_hist(df)` — 
- `metrics_current(df)` — 
- `load_inputs()` — 
- `predicate_bank(df)` — 
- `main()` — 

## hermes\scripts\v25\v331_v330_slice_full_universe_validation.py
- `load_mod(path, name)` — 
- `dn(x)` — 
- `sf(x, default)` — 
- `boolish(x)` — 
- `metrics(rows)` — 
- `pass_gate(m)` — 
- `main()` — 
- `base(r)` — 

## hermes\scripts\v25\v332_refresh_breadth_cache.py
- `dn(x)` — 
- `sf(x)` — 
- `main()` — 

## hermes\scripts\v25\v333_full_universe_rule_search_after_breadth_refresh.py
- `dn(x)` — 
- `sf(x, default)` — 
- `boolish(x)` — 
- `load_json(p, default)` — 
- `load_bars(sym)` — 
- `replay_row(r, bar_cache)` — 
- `pass_industry(df)` — 
- `metrics(df)` — 
- `gate_ok(m)` — 
- `main()` — 

## hermes\scripts\v25\v334_numeric_threshold_frontier.py
- `dn(x)` — 
- `boolish(x)` — 
- `metrics(df)` — 
- `gate(m)` — 
- `main()` — 

## hermes\scripts\v25\v335_exit_contract_frontier_after_signal_ceiling.py
- `dn(x)` — 
- `sf(x, default)` — 
- `boolish(x)` — 
- `load_json(p, default)` — 
- `load_bars(sym)` — 
- `replay_contract(r, bar_cache, sl_buf, r_mult, max_hold)` — 
- `metrics(rows)` — 
- `gate_ok(m)` — 
- `main()` — 

## hermes\scripts\v25\v336_runner_overlay_frontier.py
- `dn(x)` — 
- `sf(x, default)` — 
- `boolish(x)` — 
- `load_json(p, default)` — 
- `bars(sym)` — 
- `replay_runner(r, cache, sl_buf, tp1_r, runner_frac, tp2_r)` — 
- `metrics(rows)` — 
- `gate(m)` — 
- `main()` — 

## hermes\scripts\v25\v337_mfe_mae_ceiling_diagnosis.py
- `dn(x)` — 
- `sf(x, default)` — 
- `boolish(x)` — 
- `load_json(p, default)` — 
- `bars(sym)` — 
- `mfe_mae(r, cache, max_hold)` — 
- `summary(df)` — 
- `main()` — 

## hermes\scripts\v25\v337b_finalize_mfe_diagnosis.py
- `latest_base()` — 
- `sf(x, default)` — 
- `summary(df)` — 
- `main()` — 

## hermes\scripts\v25\v338_expansion_filter_executable_backtest.py
- `dn(x)` — 
- `sf(x, default)` — 
- `boolish(x)` — 
- `load_json(p, default)` — 
- `load_bars(sym)` — 
- `stops(r, sl_buf)` — 
- `replay_abs(r, cache, sl_buf, tp_pct, max_hold)` — 
- `replay_runner(r, cache, sl_buf, tp1_pct, runner_frac, tp2_pct)` — 
- `metrics(rows)` — 
- `pass_gate(m, g)` — 
- `main()` — 

## hermes\scripts\v25\v338_expansion_filter_exit_backtest.py
- `dn(x)` — 
- `sf(x, default)` — 
- `latest_base()` — 
- `load_json(p, default)` — 
- `load_bars(sym)` — 
- `metrics(vals, yrs)` — 
- `gate(m)` — 
- `main()` — 
- `replay(ix, tp1_abs, tp1_frac, stop_mode, max_hold, trail)` — 

## hermes\scripts\v25\v339_conservative_samebar_audit.py
- `dn(x)` — 
- `sf(x, default)` — 
- `load_json(p, default)` — 
- `latest_base()` — 
- `bars(sym)` — 
- `metrics(rows)` — 
- `gate(m)` — 
- `replay(r, b)` — 
- `main()` — 

## hermes\scripts\v25\v339_coverage_quality_frontier.py
- `dn(x)` — 
- `sf(x, default)` — 
- `boolish(x)` — 
- `load_json(p, default)` — 
- `bars(sym)` — 
- `replay(r, cache, sl_buf, tp1, frac, tp2)` — 
- `metrics(rows)` — 
- `ok(m)` — 
- `main()` — 

## hermes\scripts\v25\v340_ob_broad_exit_expansion.py
- `main()` — 

## hermes\scripts\v25\v340_shadow_candidates.py
- `dn(x)` — 
- `sf(x, default)` — 
- `load_json(p, default)` — 
- `main()` — 

## hermes\scripts\v25\v342_bsl_room_signal_layer.py
- `dn(x)` — 
- `sf(x, default)` — 
- `boolish(x)` — 
- `load_json(p, default)` — 
- `bars(sym)` — 
- `add_bsl_features(df)` — 
- `replay(r, cache, slbuf, tp1, frac, tp2)` — 
- `metrics(rows)` — 
- `gate(m)` — 
- `main()` — 

## hermes\scripts\v25\v342_fast_bsl_room_signal_layer.py
- `dn(x)` — 
- `sf(x, default)` — 
- `boolish(x)` — 
- `load_json(p, default)` — 
- `bars(sym)` — 
- `metrics(vals, yrs, reasons)` — 
- `gate(m)` — 
- `main()` — 
- `replay(i, slbuf, tp1, frac, tp2, mh)` — 
- `hi(w)` — 
- `lo(w)` — 

## hermes\scripts\v25\v342b_bsl_fast_frontier.py
- `dn(x)` — 
- `sf(x, d)` — 
- `boolish(x)` — 
- `load_json(p, d)` — 
- `bars(sym)` — 
- `metrics(vals, yrs, reasons)` — 
- `gate(m)` — 
- `replay(path, ep, zl, slbuf, tp1, frac)` — 
- `main()` — 

## hermes\scripts\v25\v343_bsl_room_deep_runner_formal.py
- `dn(x)` — 
- `sf(x, d)` — 
- `boolish(x)` — 
- `load_json(p, d)` — 
- `bars(sym)` — 
- `features(sym, ed, ep, cache)` — 
- `replay(path, ep, zl)` — 
- `calc_metrics(rows)` — 
- `gate(m)` — 
- `main()` — 

## hermes\scripts\v25\v343_dynamic_bsl_target.py
- `dn(x)` — 
- `sf(x, d)` — 
- `load_json(p, default)` — 
- `bars(sym)` — 
- `metrics(vals, yrs, reasons)` — 
- `gate(m)` — 
- `main()` — 
- `replay(i, slbuf, tp1, frac, target, fac)` — 

## hermes\scripts\v25\v344_v343_dedup_robustness.py
- `dn(x)` — 
- `sf(x, d)` — 
- `metrics(df)` — 
- `gate(m, open_n)` — 
- `choose(df, policy)` — 
- `main()` — 

## hermes\scripts\v25\v344_v343_robustness_audit.py
- `dn(x)` — 
- `sf(x, d)` — 
- `metrics(df)` — 
- `gate(m)` — 
- `main()` — 

## hermes\scripts\v25\v345_v343_cost_stress.py
- `metrics(df, cost)` — 
- `gate(m, open_n)` — 
- `main()` — 

## hermes\scripts\v25\v347_target_space_oos_search.py
- `dn(x)` — 
- `sf(x, d)` — 
- `load_json(p, d)` — 
- `json_text(value)` — 
- `bars(sym)` — 
- `replay(ep, zl, path, target_pct, hold)` — 
- `metrics(frame)` — 
- `hard_pass(m)` — 
- `main()` — 

## hermes\scripts\v25\v347_target_space_robustness.py
- `dn(x)` — 
- `sf(x, d)` — 
- `load_json(p, d)` — 
- `bars(sym)` — 
- `replay(x, target, fac, hold)` — 
- `metrics(data)` — 
- `passed(m)` — 
- `main()` — 

## hermes\scripts\v25\v348_causal_sequence_rebuild_audit.py
- `f(x, d)` — 
- `ds(x)` — 
- `bv(b, k)` — 
- `date(b)` — 
- `bars(path)` — 
- `symbol(path)` — 
- `trend(ks, i)` — 
- `last_bearish(ks, i)` — 
- `ssl_sweep(ks, i)` — 
- `event(ks, i, state)` — 
- `poi(ks, i, ev)` — 
- `entry(ks, i, p)` — 
- `replay(ks, e, p)` — 
- `metrics(df)` — 
- `passed(m)` — 
- `main()` — 

## hermes\scripts\v25\v349_post_reclaim_confirmation_diagnosis.py
- `ds(x)` — 
- `f(x, d)` — 
- `load(p)` — 
- `bars(sym)` — 
- `met(x)` — 
- `ok(m)` — 
- `main()` — 

## hermes\scripts\v25\v350_confirmed_swing_displacement_audit.py
- `atr(ks, i)` — 
- `pivots(ks, i)` — 
- `event(ks, i, state, all_hs, all_ls)` — 
- `main()` — 

## hermes\scripts\v25\v351_semantic_oracle_daily_audit.py
- `num(bar, key)` — 
- `day(bar)` — 
- `load(path)` — 
- `symbol(path)` — 
- `atr(ks, i, period)` — 
- `validate_swings(ks, swings)` — 
- `validate_structure(ks, swings, events)` — 
- `validate_fvgs(ks, fvgs)` — 
- `validate_sweeps(ks, swings, sweeps)` — 
- `validate_obs(ks, events, obs)` — 
- `candidate_seed(sym, ks, signals, semantic_bad)` — 
- `main()` — 

## hermes\scripts\v25\v352_continuation_candidate_lifecycle.py
- `f(x)` — 
- `ds(x)` — 
- `bars(sym)` — 
- `lifecycle(ks, seed)` — 
- `main()` — 

## hermes\scripts\v25\v353_persistent_takeover_audit.py
- `f(x)` — 
- `d(b)` — 
- `bars(sym)` — 
- `persistent(ks, row)` — 
- `main()` — 

## hermes\scripts\v25\v354_lifecycle_setup_identity_audit.py
- `dkey(value)` — 
- `latest_daily_dates()` — 
- `path_key(row)` — Same OB plus same observed resolution is one setup path, not many BOS rows.
- `representative(rows)` — 
- `main()` — 

## hermes\scripts\v25\v355_current_lifecycle_frontier_audit.py
- `i(value)` — 
- `zone_key(row)` — Same OB should have one fixed zone; retain any differing zone as a conflict.
- `base_key(row)` — 
- `rank(row)` — 
- `no_outcome_columns(rows)` — 
- `main()` — 

## hermes\scripts\v25\v356_independent_semantic_oracle_differential.py
- `f(value)` — 
- `day(bar)` — 
- `symbol(path)` — 
- `load(path)` — 
- `oracle_swings(ks)` — 
- `oracle_structure(ks, swings)` — 
- `oracle_fvgs(ks)` — 
- `oracle_sweeps(ks, swings)` — 
- `oracle_obs(ks, events)` — 
- `key(stage, row)` — 
- `diff(sym, stage, actual, oracle, output, counts)` — 
- `seed_keys(rows)` — 
- `main()` — 

## hermes\scripts\v25\v357_canonical_continuation_lifecycle.py
- `f(value)` — 
- `day(bar)` — 
- `load_bars(symbol)` — 
- `state_before_event(bars, ob_idx, event_idx, low, high)` — Classify zone strictly before the BOS bar; event bar is not inspected.
- `lifecycle_after_event(bars, event_idx, low, high)` — Causal post-BOS lifecycle; event bar is known at seed time, so start after it.
- `main()` — 

## hermes\scripts\v25\v357_persistent_takeover_daily_t1_replay.py
- `f(x)` — 
- `date_of(bar)` — 
- `load_bars(symbol)` — 
- `confirmed_swing_high_target(bars, confirmation_idx, entry)` — Nearest high that was confirmed by the information cutoff, never future data.
- `replay(bars, row)` — 
- `metrics(rows)` — 
- `main()` — 
- `brief(group)` — 

## hermes\scripts\v25\v358_unique_persistent_takeover_daily_t1_replay.py
- `f(x)` — 
- `date_of(bar)` — 
- `load_bars(symbol)` — 
- `confirmed_swing_high_target(bars, confirmation_idx, entry)` — Nearest high that was confirmed by the information cutoff, never future data.
- `replay(bars, row)` — 
- `metrics(rows)` — 
- `main()` — 
- `brief(group)` — 

## hermes\scripts\v25\v359_persistent_takeover_semantic_failure_audit.py
- `num(value)` — 
- `day(bar)` — 
- `bars(symbol)` — 
- `signals(ks)` — 
- `binned_stats(rows)` — 
- `main()` — 

## hermes\scripts\v25\v360_canonical_persistent_takeover_daily_t1_replay.py
- `date_of(bar)` — 
- `load_bars(symbol)` — 
- `persistent(bars, row)` — Two post-takeover closes above the zone; no future bars are inspected.
- `brief(rows)` — 
- `main()` — 

## hermes\scripts\v25\v365_v333_rule_walkforward_closure.py
- `boolish(x)` — 
- `metric(df)` — 
- `passes(m, gate)` — 
- `predicates(df)` — 
- `main()` — 

## hermes\scripts\v25\v366_v365_candidate_causality_audit.py
- `boolean(s)` — 
- `stats(df)` — 
- `main()` — 

## hermes\scripts\v25\v367_causal_v132_reentry_walkforward.py
- `boolish(x)` — 
- `kline(symbol, cache)` — 
- `metric(df)` — 
- `passes(m, gate)` — 
- `predicates(df)` — 
- `main()` — 

## hermes\scripts\v25\v368_v367_independent_causality_audit.py
- `date_of(bar)` — 
- `main()` — 

## hermes\scripts\v25\v370_baostock_m60_full_source_audit.py
- `universe()` — 
- `norm_date(s)` — 
- `fetch(code, exch)` — 
- `main()` — 

## hermes\scripts\v25\v371_baostock_m60_strict_coverage_audit.py
- `ds(value)` — 
- `universe()` — 
- `query_chunk(bs_code, start_date, end_date)` — Read one capped calendar chunk; retry only an expired Baostock session.
- `worker_init()` — 
- `fetch_one(item)` — 
- `main()` — 

## hermes\scripts\v25\v371_sina_m60_dataset_build.py
- `universe()` — 
- `output_path(code, exchange)` — 
- `usable_existing(path)` — 
- `quality(rows)` — 
- `fetch(item)` — 
- `main()` — 

## hermes\scripts\v25\v372_baostock_m60_qfq_alignment_audit.py
- `ds(value)` — 
- `f(value)` — 
- `source_pass()` — 
- `universe()` — 
- `query_chunk(bs_code, start, end)` — 
- `worker_init()` — 
- `fetch_one(item)` — 
- `main()` — 

## hermes\scripts\v25\v373_sina_m60_strict_coverage_audit.py
- `date_of(value)` — 
- `read_json(path)` — 
- `expected_days(path)` — 
- `check(path, code, exchange)` — 
- `main()` — 

## hermes\scripts\v25\v374_m60_causal_retest_generator.py
- `f(x)` — 
- `day(t)` — 
- `load(path)` — 
- `pivots(bars)` — 3-left/3-right pivots scheduled at their first observable bar.
- `nearest_bear_ob(bars, start, event)` — 
- `replay(bars, entry_i, sl, tp)` — 
- `one_symbol(symbol, path)` — 
- `metrics(rows)` — 
- `main()` — 

## hermes\scripts\v25\v375_m60_nearest_swing_mss_generator.py
- `f(x)` — 
- `day(t)` — 
- `load(path)` — 
- `pivots(bars)` — 3-left/3-right pivots scheduled at their first observable bar.
- `nearest_bear_ob(bars, start, event)` — 
- `replay(bars, entry_i, sl, tp)` — 
- `one_symbol(symbol, path)` — 
- `metrics(rows)` — 
- `main()` — 

## hermes\scripts\v25\v376_m60_nearest_swing_mss_serial_execution.py
- `f(x)` — 
- `day(t)` — 
- `load(path)` — 
- `pivots(bars)` — 3-left/3-right pivots scheduled at their first observable bar.
- `nearest_bear_ob(bars, start, event)` — 
- `replay(bars, entry_i, sl, tp)` — 
- `one_symbol(symbol, path)` — 
- `metrics(rows)` — 
- `main()` — 

## hermes\scripts\v25\v377_m60_po3_accumulation_distribution.py
- `f(x)` — 
- `day(t)` — 
- `load(path)` — 
- `pivots(bars)` — 3-left/3-right pivots scheduled at their first observable bar.
- `nearest_bear_ob(bars, start, event)` — 
- `replay(bars, entry_i, sl, tp)` — 
- `one_symbol(symbol, path)` — 
- `metrics(rows)` — 
- `main()` — 

## hermes\scripts\v25\v379_sina_m60_raw_daily_data_gate.py
- `day(value)` — 
- `f(value)` — 
- `universe()` — 
- `legacy_dates(path)` — 
- `listing_metadata()` — Listing date and current-list membership are metadata, never POI inputs.
- `read_m60(symbol)` — 
- `daily_from_m60(groups, invalid, market_index)` — 
- `main()` — 

## hermes\scripts\v25\v380_raw_daily_independent_semantic_oracle.py
- `f(x)` — 
- `load(path)` — 
- `independent(b)` — 
- `reference(b)` — 
- `key(stage, x)` — 
- `main()` — 

## hermes\scripts\v25\v381_true_mtf_raw_daily_poi_m60_replay.py
- `f(x)` — 
- `m60(sym)` — 
- `daily(sym)` — 
- `pivots(b)` — 
- `candidate(seed, ib, db, highs)` — 
- `exitrow(r, ib)` — 
- `metrics(x)` — 
- `main()` — 

## hermes\scripts\v25\v382_pit_cross_sectional_participation_gate.py
- `f(x)` — 
- `main()` — 

## hermes\scripts\v25\v383_pit_participation_outcome_replay.py
- `metrics(rows)` — 
- `main()` — 

## hermes\scripts\v25\v384_pit_behavior_cohort_data_gate.py
- `symbol(path, suffix)` — 
- `main()` — 

## hermes\scripts\v25\v385_pit_behavior_cohort_outcome_replay.py
- `stats(rows)` — 
- `main()` — 

## hermes\scripts\v25\v386_pit_disclosure_availability_gate.py
- `stamp(value)` — 
- `code(symbol)` — 
- `fetch(session, codes, start, end)` — 
- `main()` — 

## hermes\scripts\v25\v387_pit_disclosure_event_schema.py
- `stamp(value)` — 
- `code(symbol)` — 
- `classify(title)` — 
- `fetch(session, codes, start, end)` — 
- `main()` — 

## hermes\scripts\v25\v388_pit_disclosure_outcome_replay.py
- `stats(rows)` — 
- `main()` — 

## hermes\scripts\v25\v389_pit_disclosure_exact_window_schema.py
- `stamp(value)` — 
- `code(symbol)` — 
- `classify(title)` — 
- `fetch(session, codes, start, end)` — 
- `main()` — 

## hermes\scripts\v25\v390_pit_disclosure_exact_window_outcome_replay.py
- `stats(rows)` — 
- `main()` — 

## hermes\scripts\v25\v391_pit_fundamental_disclosure_walkforward.py
- `stats(rows)` — 
- `select(rows, years, state)` — 
- `main()` — 

## hermes\scripts\v25\v392_pit_disclosure_window_robustness.py
- `stamp(value)` — 
- `code(symbol)` — 
- `classify(title)` — 
- `fetch(session, codes, start, end)` — 
- `state_for(announcements, cutoff, days)` — 
- `stats(rows)` — 
- `main()` — 

## hermes\scripts\v25\v393_pit_lhb_availability_gate.py
- `fetch_year(session, year)` — 
- `main()` — 

## hermes\scripts\v25\v394_pit_lhb_outcome_replay.py
- `stats(rows)` — 
- `state(row)` — 
- `main()` — 

## hermes\scripts\v25\v395_pit_margin_financing_availability_and_replay.py
- `d8(value)` — 
- `pct(n, d)` — 
- `metrics(rows)` — 
- `prior_weekday(date)` — 
- `fetch_exchange(date, exchange)` — 
- `fetch_pit_day(hold_date)` — Find the latest exchange date strictly before hold; retry weekdays for holidays.
- `main()` — 

## hermes\scripts\v25\v397_pit_fund_holdings_availability_gate.py
- `watermark(period)` — 
- `d8(value)` — 
- `periods()` — 
- `select_period(hold_date, available)` — 
- `main()` — 

## hermes\scripts\v25\v398_pit_etf_share_change_availability_gate.py
- `probe_sse(day)` — 
- `probe_szse(day)` — 
- `main()` — 

## hermes\scripts\v25\v399_pit_shareholder_holdings_feasibility.py
- `clean_date(value)` — 
- `report_end(title)` — 
- `prefix(symbol)` — 
- `fixed_identities()` — 
- `get_json(url, params)` — Retry Eastmoney's transient HTML anti-bot pages; never treat them as no data.
- `announcements(symbol)` — 
- `holder_snapshot(key)` — 
- `main()` — 

## hermes\scripts\v25\v400_announcement_metadata_recovery_pilot.py
- `fetch_symbol(symbol)` — 
- `main()` — 

## hermes\scripts\v25\v401_pit_shareholder_metadata_full_recovery.py
- `load_v400()` — 
- `digits(value)` — 
- `report_end(title)` — 
- `main()` — 

## hermes\scripts\v25\v402_pit_shareholder_feature_materialization.py
- `prefix(symbol)` — 
- `f(value)` — 
- `snapshot(key)` — 
- `features(rows)` — 
- `main()` — 

## hermes\scripts\v25\v403_pit_shareholder_frozen_outcome_replay.py
- `truth(value)` — 
- `stats(rows)` — 
- `uplift(candidate, baseline)` — 
- `passes(candidate, diff)` — 
- `main()` — 
- `one(values)` — 

## hermes\scripts\v25\v404_pit_block_trade_availability_gate.py
- `fetch_year(session, year)` — 
- `main()` — 

## hermes\scripts\v25\v405_pit_block_trade_frozen_outcome_replay.py
- `metrics(rows)` — 
- `state(row)` — 
- `uplift(item, base)` — 
- `epoch_metrics(rows, prefix)` — 
- `main()` — 

## hermes\scripts\v25\v406_pit_northbound_holdings_availability_gate.py
- `fetch(target)` — 
- `main()` — 

## hermes\scripts\v25\v407_pit_tick_history_availability_gate.py
- `ds(value)` — 
- `daily_close(symbol, date)` — 
- `fingerprint(df)` — 
- `inspect(client, symbol, date)` — 
- `main()` — 

## hermes\scripts\v25\v408_eastmoney_intraday_history_availability.py
- `secid(symbol)` — 
- `fetch(session, symbol, day, klt)` — 
- `main()` — 

## hermes\scripts\v25\v409_causal_signal_combination_state_machine.py
- `f(x)` — 
- `day(bar)` — 
- `load(path)` — 
- `symbol(path)` — 
- `lifecycle(ks, event_i, low, high)` — First post-confirmation touch/reclaim/hold; a close below zone kills setup.
- `obs_by_event(obs)` — 
- `valid_reversal_rows(sym, ks, signals)` — R1/R2: SSL must precede bull CHOCH by 1..20 confirmed bars.
- `valid_continuation_rows(sym, ks, signals)` — C1: confirmed bull BOS plus its causal backward-anchored demand OB.
- `seed(sym, ks, combo, sweep_i, event_i, poi_i)` — 
- `q50(values)` — 
- `main()` — 
- `date_at(i)` — 

## hermes\scripts\v25\v410_frozen_combo_t1_mark_replay.py
- `f(x)` — 
- `day(bar)` — 
- `load(symbol)` — 
- `pct(a, b)` — 
- `metric(rows, horizon)` — 
- `main()` — 

## hermes\scripts\v25\v411_combo_yearly_stability_closure.py
- `metric(rows, horizon)` — 
- `passes(x)` — 
- `main()` — 

## hermes\scripts\v25\v412_baostock_subhourly_access_gate.py
- `main()` — 

## hermes\scripts\v25\v413_research_program_closure_audit.py
- `load(name)` — 
- `text_of(data)` — 
- `classify(kind, data)` — 
- `main()` — 

## hermes\scripts\v25\v415_poi_lifecycle_integrity_audit.py
- `f(value)` — 
- `day(bar)` — 
- `load_bars(symbol, cache)` — 
- `lifecycle(bars, start_idx, low, high)` — First fresh touch/reclaim/hold strictly after all prerequisites exist.
- `source_state(row, bars)` — Classify whether V409's stated post-confirmation lifecycle was legal.
- `main()` — 

## hermes\scripts\v25\v415_structure_flip_poi_lifecycle.py
- `f(value)` — 
- `day(bar)` — 
- `load(path)` — 
- `symbol(path)` — 
- `lifecycle(bars, event_idx, zone_low, zone_high)` — 
- `make_row(sym, bars, combo, event, sweep_idx)` — 
- `median_int(rows, field)` — 
- `main()` — 
- `date_at(idx)` — 

## hermes\scripts\v25\v416_strict_semantic_combination_rebuild.py
- `key(row)` — 
- `main()` — 

## hermes\scripts\v25\v416_structure_flip_frozen_t1_replay.py
- `f(value)` — 
- `day(bar)` — 
- `load(symbol)` — 
- `target_before_entry(swings, takeover_idx, entry_price)` — 
- `simulate(seed, bars, swings)` — 
- `metrics(rows)` — 
- `main()` — 

## hermes\scripts\v25\v417_post_reclaim_expansion_lifecycle.py
- `f(value)` — 
- `day(bar)` — 
- `load(symbol)` — 
- `main()` — 

## hermes\scripts\v25\v417_strict_semantic_frozen_t1_replay.py
- `f(x)` — 
- `day(bar)` — 
- `load(symbol)` — 
- `pct(a, b)` — 
- `metrics(rows, horizon)` — 
- `passes(x)` — 
- `main()` — 

## hermes\scripts\v25\v418_post_reclaim_expansion_frozen_t1_replay.py
- `f(value)` — 
- `day(bar)` — 
- `load(symbol)` — 
- `target_before_entry(swings, signal_idx, entry_price)` — 
- `simulate(seed, bars, swings)` — 
- `metrics(rows)` — 
- `main()` — 

## hermes\scripts\v25\v418_strict_semantic_closure_correction.py
- `main()` — 

## hermes\scripts\v25\v419_strict_semantic_replay_integrity_audit.py
- `f(x)` — 
- `day(bar)` — 
- `load(symbol)` — 
- `key(row)` — 
- `main()` — 

## hermes\scripts\v25\v420_eql_pool_reversal_generator.py
- `f(x)` — 
- `day(b)` — 
- `load(path)` — 
- `symbol(path)` — 
- `lifecycle(ks, start, low, high)` — Return lifecycle state plus ordered touch/reclaim/takeover indices.
- `pool_sweeps(swings, sweeps)` — A pool is two confirmed prior swing lows within the fixed 0.3% sweep band.
- `main()` — 

## hermes\scripts\v25\v420_eql_spring_sos_lps_generator.py
- `f(x)` — 
- `day(b)` — 
- `load(path)` — 
- `symbol(path)` — 
- `pivots(ks)` — 
- `lifecycle(ks, start, low, high)` — 
- `scan(path_str)` — 
- `main()` — 

## hermes\scripts\v25\v421_eql_pool_reversal_frozen_t1_replay.py
- `f(x)` — 
- `day(bar)` — 
- `load(symbol)` — 
- `pct(price, entry)` — 
- `metrics(rows, horizon)` — 
- `annual_gate(metrics_by_year)` — 
- `main()` — 

## hermes\scripts\v25\v421_eql_spring_frozen_structural_replay.py
- `f(x)` — 
- `day(b)` — 
- `load(sym)` — 
- `confirmed_highs(ks, visible_i)` — 
- `metrics(rows)` — 
- `main()` — 

## hermes\scripts\v25\v422_failed_breakdown_breaker_generator.py
- `f(x)` — 
- `day(b)` — 
- `sym(path)` — 
- `load(path)` — 
- `swing_lows(ks)` — 
- `lifecycle(ks, start, low, high)` — 
- `scan(path_s)` — 
- `main()` — 

## hermes\scripts\v25\v423_failed_breakdown_frozen_replay.py
- `f(x)` — 
- `day(b)` — 
- `load(sym)` — 
- `highs(ks)` — 
- `met(rows)` — 
- `main()` — 

## hermes\scripts\v25\v423_range_accumulation_breaker_generator.py
- `f(x)` — 
- `day(b)` — 
- `load(path)` — 
- `symbol(path)` — 
- `lifecycle(ks, start, low, high)` — First post-breaker retest -> reclaim -> next hold; close below zone invalidates.
- `range_candidates(swings, ks)` — Two confirmed highs and lows form a prior balance; no outcome-dependent selection.
- `fresh_bearish_breaker(ks, sweep_i, break_i)` — Last bearish breaker at/after SSL and before range-high break, unmitigated pre-break.
- `main()` — 

## hermes\scripts\v25\v424_failed_breakdown_hierarchical_replay.py
- `f(x)` — 
- `day(b)` — 
- `load(sym)` — 
- `highs(ks)` — 
- `met(rows)` — 
- `main()` — 

## hermes\scripts\v25\v424_range_accumulation_breaker_integrity_audit.py
- `f(x)` — 
- `day(b)` — 
- `load(sym)` — 
- `lifecycle(ks, start, low, high)` — 
- `main()` — 

## hermes\scripts\v25\v425_new_direction_integrity_audit.py
- `report(name)` — 
- `rows(r)` — 
- `iv(x)` — 
- `day(b)` — 
- `audit_seed(data, order, forbidden)` — 
- `audit_trade(data)` — 
- `main()` — 

## hermes\scripts\v25\v425_range_accumulation_breaker_frozen_t1_replay.py
- `f(x)` — 
- `day(b)` — 
- `load(sym)` — 
- `pct(price, entry)` — 
- `metrics(rows, horizon)` — 
- `passes(x)` — 
- `main()` — 

## hermes\scripts\v25\v427_po3_breaker_generator.py
- `f(x)` — 
- `day(b)` — 
- `load(p)` — 
- `sym(p)` — 
- `lifecycle(ks, start, low, high)` — 
- `fresh_breaker(ks, sweep, event)` — 
- `main()` — 

## hermes\scripts\v25\v428_po3_breaker_integrity_audit.py
- `f(x)` — 
- `day(b)` — 
- `load(s)` — 
- `lifecycle(ks, start, lo, hi)` — 
- `main()` — 

## hermes\scripts\v25\v429_po3_breaker_frozen_t1_replay.py
- `f(x)` — 
- `day(b)` — 
- `load(sym)` — 
- `pct(price, entry)` — 
- `metrics(rows, horizon)` — 
- `passes(x)` — 
- `main()` — 

## hermes\scripts\v25\v431_local_daily_structure_frontier_closure_audit.py
- `load(path)` — 
- `main()` — 

## hermes\scripts\v25\v432_v185_causality_provenance_audit.py
- `i(value)` — 
- `main()` — 

## hermes\scripts\v25\v433_v365_negative_control_shadow.py
- `load(name)` — 
- `main()` — 

## hermes\scripts\v25\v434_supply_failure_breaker_generator.py
- `f(value)` — 
- `day(bar)` — 
- `load(path)` — 
- `symbol(path)` — 
- `at(ks, idx)` — 
- `lifecycle(ks, anchor_i, low, high)` — 
- `one_symbol(sym, ks)` — 
- `main()` — 

## hermes\scripts\v25\v435_supply_failure_breaker_independent_oracle.py
- `f(value)` — 
- `day(bar)` — 
- `load_bars(path)` — 
- `symbol(path)` — 
- `confirmed_swings(bars)` — 
- `structure_events(bars, highs, lows)` — 
- `supply_obs(bars, events)` — 
- `breaker_lifecycle(bars, ob)` — 
- `identity(row)` — 
- `main()` — 
- `integer(value)` — 

## hermes\scripts\v25\v436_supply_failure_breaker_frozen_t1_replay.py
- `f(value)` — 
- `day(bar)` — 
- `load_bars(symbol)` — 
- `confirmed_highs(bars)` — 
- `known_target(highs, cutoff_idx, entry)` — 
- `replay(row, bars, highs)` — 
- `stats(rows)` — 
- `gate_pass(overall, yearly, epochs, t1)` — 
- `main()` — 

## hermes\scripts\v25\v437_target_first_dol_generator.py
- `f(value)` — 
- `day(bar)` — 
- `load_bars(path)` — 
- `symbol(path)` — 
- `choose_dol(bars, confirmed_highs, event_idx)` — Nearest BSL above event close, visible and still unconsumed before event.
- `demand_poi(bars, event_idx)` — Nearest bearish candle before the same bullish event.
- `lifecycle(bars, event_idx, zone_low, zone_high, dol_price)` — 
- `at(bars, idx)` — 
- `semantic_order_valid(dol_confirm_idx, poi_idx, event_idx, result)` — Check information visibility, not the POI candle's historical position.
- `one_symbol(sym, bars)` — 
- `main()` — 

## hermes\scripts\v25\v438_target_first_dol_independent_oracle.py
- `f(value)` — 
- `day(bar)` — 
- `load_bars(path)` — 
- `symbol(path)` — 
- `confirmed_swings(bars)` — 
- `structure_events(bars, highs, lows)` — 
- `choose_dol(bars, highs, event_idx)` — 
- `demand_poi(bars, event_idx)` — 
- `lifecycle(bars, event_idx, zone_low, zone_high, dol_price)` — 
- `identity(row)` — 
- `main()` — 

## hermes\scripts\v25\v439_target_first_dol_frozen_t1_replay.py
- `f(value)` — 
- `day(bar)` — 
- `load_bars(symbol)` — 
- `replay(row, bars)` — 
- `stats(rows)` — 
- `gate_pass(overall, yearly, epochs, t1)` — 
- `main()` — 

## hermes\scripts\v25\v440_protected_swing_transfer_generator.py
- `f(value)` — 
- `day(bar)` — 
- `load_bars(path)` — 
- `symbol(path)` — 
- `protected_transfer(bars, confirmed_lows, previous_event_idx, event_idx)` — 
- `demand_poi(bars, event_idx, new_swing_idx)` — 
- `lifecycle_detail(bars, event_idx, zone_low, zone_high, protected_low)` — 
- `lifecycle(bars, event_idx, zone_low, zone_high, protected_low)` — 
- `at(bars, idx)` — 
- `one_symbol(sym, bars)` — 
- `main()` — 

## hermes\scripts\v25\v441_protected_swing_transfer_independent_oracle.py
- `f(x)` — 
- `day(b)` — 
- `load_bars(path)` — 
- `symbol(path)` — 
- `confirmed_swings(bars)` — 
- `structure_events(bars, highs, lows)` — 
- `protected_transfer(bars, lows, previous_event_idx, event_idx)` — 
- `demand_poi(bars, event_idx, new_idx)` — 
- `lifecycle(bars, event, low, high, protected)` — 
- `identity(r)` — 
- `main()` — 

## hermes\scripts\v25\v442_protected_swing_transfer_frozen_t1_replay.py
- `f(x)` — 
- `day(b)` — 
- `load_bars(sym)` — 
- `confirmed_highs(bars)` — 
- `known_unconsumed_target(highs, bars, cutoff, entry)` — 
- `replay(row, bars, highs)` — 
- `stats(rows)` — 
- `gate_pass(o, y, e, t1)` — 
- `main()` — 

## hermes\scripts\v25\v444_internal_liquidity_ifvg_frontier.py
- `f(x)` — 
- `day(b)` — 
- `load(path)` — 
- `sym(path)` — 
- `pivots(bars, left, right)` — 
- `nearest_known_high(ext_highs, cutoff, entry)` — 
- `idm_rows(symbol, bars, ext_h, ext_l, int_h, int_l)` — 
- `ifvg_rows(symbol, bars)` — 
- `replay(row, bars, ext_h)` — 
- `stats(rows)` — 
- `pass_gate(overall, yearly, t1)` — 
- `main()` — 

## hermes\scripts\v25\v445_v444_independent_integrity_audit.py
- `f(x)` — 
- `bars(s)` — 
- `main()` — 

## hermes\scripts\v25\v446_ssl_created_ifvg_reversal.py
- `f(x)` — 
- `load(s)` — 
- `lows(b)` — 
- `metrics(rows)` — 
- `main()` — 

## hermes\scripts\v25\v447_ssl_bpr_reversal_generator.py
- `f(x)` — 
- `day(b)` — 
- `load(path)` — 
- `symbol(path)` — 
- `confirmed_lows(bars)` — 
- `generate(sym, bars)` — 
- `main()` — 

## hermes\scripts\v25\v448_ssl_bpr_independent_oracle.py
- `f(x)` — 
- `i(x)` — 
- `day(x)` — 
- `load(sym)` — 
- `close(a, b)` — 
- `verify(row, bars)` — 
- `main()` — 

## hermes\scripts\v25\v449_ssl_bpr_frozen_t1_replay.py
- `f(x)` — 
- `i(x)` — 
- `day(x)` — 
- `load(sym)` — 
- `confirmed_highs(bars)` — 
- `target_before_entry(bars, highs, takeover, entry)` — 
- `replay(seed, bars, highs)` — 
- `stats(rows)` — 
- `main()` — 

## hermes\scripts\v25\v450_eqh_compression_generator.py
- `f(x)` — 
- `d(b)` — 
- `load(p)` — 
- `piv(b, key)` — 
- `sym(p)` — 
- `gen(s, b)` — 
- `main()` — 

## hermes\scripts\v25\v452_unicorn_ssl_breaker_fvg_generator.py
- `f(value)` — 
- `day(bar)` — 
- `load(path)` — 
- `symbol(path)` — 
- `bull_fvgs(bars)` — 
- `first_lifecycle(bars, born, zone_low, zone_high, ssl_low)` — 
- `one_symbol(sym, bars)` — 
- `main()` — 

## hermes\scripts\v25\v453_turtle_soup_ssl_reversal_generator.py
- `f(x)` — 
- `day(b)` — 
- `load(path)` — 
- `symbol(path)` — 
- `confirmed_lows(bars)` — 
- `generate(sym, bars)` — 
- `main()` — 

## hermes\scripts\v25\v454_turtle_soup_independent_oracle.py
- `f(x)` — 
- `i(x)` — 
- `ds(x)` — 
- `load(sym)` — 
- `close(a, b)` — 
- `verify(row, bars)` — 
- `main()` — 

## hermes\scripts\v25\v455_turtle_soup_frozen_t1_replay.py
- `f(x)` — 
- `i(x)` — 
- `ds(x)` — 
- `load(sym)` — 
- `confirmed_highs(bars)` — 
- `target_at(highs, cutoff, entry)` — 
- `replay(seed, bars, highs)` — 
- `stats(rows)` — 
- `gate_pass(overall, yearly, t1)` — 
- `main()` — 

## hermes\scripts\v25\v457_weekly_ssl_rejection_block_generator.py
- `f(value)` — 
- `ds(value)` — 
- `load_daily(path)` — 
- `symbol(path)` — 
- `completed_weeks(daily)` — 
- `confirmed_weekly_lows(weeks)` — 
- `lifecycle(daily, raid_end_date, zone_low, zone_high)` — 
- `generate(sym, daily)` — 
- `main()` — 

## hermes\scripts\v25\v458_weekly_rejection_block_independent_oracle.py
- `number(value)` — 
- `integer(value)` — 
- `date_string(value)` — 
- `raw_daily(sym)` — 
- `weekly_bars(daily)` — 
- `is_weekly_low(weeks, idx)` — 
- `same_price(left, right)` — 
- `first_lifecycle(daily, raid_end, low, high)` — 
- `verify(row, daily)` — 
- `main()` — 

## hermes\scripts\v25\v459_weekly_rejection_block_frozen_t1_replay.py
- `f(value)` — 
- `integer(value)` — 
- `ds(value)` — 
- `load_daily(sym)` — 
- `completed_weeks(daily)` — 
- `confirmed_weekly_highs(weeks)` — 
- `target_at(highs, weeks, cutoff_date, entry)` — 
- `replay(seed, daily, weeks, highs)` — 
- `stats(rows)` — 
- `promotion_pass(overall, yearly, t1_violations)` — 
- `main()` — 

## hermes\scripts\v25\v461_market_smt_turtle_soup_generator.py
- `f(x)` — 
- `ds(x)` — 
- `load(path)` — 
- `market_composite()` — 
- `confirmed_lows(bars)` — 
- `smt_context(market, lows, date)` — 
- `main()` — 

## hermes\scripts\v25\v462_market_smt_independent_oracle.py
- `num(x)` — 
- `date(x)` — 
- `rawbars(path)` — 
- `rebuild_index()` — 
- `pivots(bars)` — 
- `oracle_pass(index, lows, raid_date)` — 
- `key(row)` — 
- `main()` — 

## hermes\scripts\v25\v463_market_smt_frozen_t1_replay.py
- `delta(current, base)` — 
- `main()` — 

## hermes\scripts\v25\v464_market_smt_direction_closure.py

## hermes\scripts\v25\v465_industry_smt_turtle_soup_generator.py
- `f(x)` — 
- `ds(x)` — 
- `symbol(path)` — 
- `load(path)` — 
- `build_source()` — 
- `ex_stock_index(sym, ind, sums, own)` — 
- `lows(bars)` — 
- `context(index, pivots, date)` — 
- `main()` — 

## hermes\scripts\v25\v466_industry_smt_independent_oracle.py
- `n(x)` — 
- `d(x)` — 
- `sym(path)` — 
- `bars(path)` — 
- `source_tables()` — 
- `composite(s, ind, totals, single)` — 
- `pivots(seq)` — 
- `qualifies(seq, pivs, raid_date)` — 
- `key(r)` — 
- `main()` — 

## hermes\scripts\v25\v467_industry_smt_frozen_t1_replay.py
- `delta(current, base)` — 
- `main()` — 

## hermes\scripts\v25\v468_industry_smt_direction_closure.py

## hermes\scripts\v25\v469_industry_lead_stock_lag_generator.py
- `industry_events(bars)` — 
- `lead_context(bars, events, stock_raid_date)` — 
- `main()` — 

## hermes\scripts\v25\v470_industry_lead_stock_lag_oracle.py
- `index_without_stock(sym, industry, sums, own)` — 
- `pivots(rows)` — 
- `events(rows)` — 
- `select(rows, evs, date)` — 
- `main()` — 

## hermes\scripts\v25\v471_industry_lead_stock_lag_frozen_t1_replay.py
- `delta(cur, base)` — 
- `main()` — 

## hermes\scripts\v25\v472_industry_lead_stock_lag_closure.py
- `f(x)` — 
- `stats(rows)` — 
- `main()` — 

## hermes\scripts\v25\v473_inducement_sweep_continuation_generator.py
- `f(x)` — 
- `ds(x)` — 
- `load(path)` — 
- `symbol(path)` — 
- `pivots(bars, key)` — 
- `contexts(bars)` — 
- `generate(sym, bars)` — 
- `main()` — 

## hermes\scripts\v25\v474_inducement_sweep_independent_oracle.py
- `f(x)` — 
- `ii(x)` — 
- `ds(x)` — 
- `load(sym)` — 
- `pivot(bars, idx, key)` — 
- `close(a, b)` — 
- `eligible_contexts(bars, raid)` — 
- `verify(r, bars)` — 
- `main()` — 

## hermes\scripts\v25\v475_inducement_sweep_frozen_t1_replay.py
- `f(x)` — 
- `ii(x)` — 
- `ds(x)` — 
- `load(sym)` — 
- `highs(bars)` — 
- `target_at(items, cutoff, entry)` — 
- `replay(seed, bars, hh)` — 
- `stats(rows)` — 
- `gate(overall, yearly, t1)` — 
- `main()` — 

## hermes\scripts\v25\v476_inducement_sweep_direction_closure.py
- `f(x)` — 
- `stats(rows)` — 
- `main()` — 

## hermes\scripts\v25\v477_double_ssl_absorption_generator.py
- `f(x)` — 
- `ds(x)` — 
- `load(path)` — 
- `symbol(path)` — 
- `confirmed_lows(bars)` — 
- `generate(sym, bars)` — 
- `main()` — 

## hermes\scripts\v25\v478_double_ssl_absorption_oracle.py
- `f(x)` — 
- `ds(x)` — 
- `bars_for(sym)` — 
- `pivots_low(b)` — 
- `rebuild(sym, b)` — 
- `equal(a, b, key)` — 
- `main()` — 

## hermes\scripts\v25\v479_double_ssl_absorption_frozen_t1_replay.py
- `f(x)` — 
- `i(x)` — 
- `ds(x)` — 
- `load(sym)` — 
- `confirmed_highs(bars)` — 
- `target_at(highs, cutoff, entry)` — 
- `replay(seed, bars, highs)` — 
- `stats(rows)` — 
- `pass_gate(overall, yearly, t1)` — 
- `main()` — 

## hermes\scripts\v25\v480_double_ssl_absorption_direction_closure.py
- `f(x)` — 
- `stats(rows)` — 
- `compare(expected, observed, fields)` — 
- `main()` — 

## hermes\scripts\v25\v481_two_sided_liquidity_purge_generator.py
- `f(x)` — 
- `ds(x)` — 
- `load(path)` — 
- `symbol(path)` — 
- `pivots(bars, field, high)` — 
- `generate(sym, bars)` — 
- `main()` — 

## hermes\scripts\v25\v482_two_sided_liquidity_purge_independent_oracle.py
- `num(x)` — 
- `date(x)` — 
- `read_bars(sym)` — 
- `independent_pivots(bars, is_high)` — 
- `derive(sym, bars)` — 
- `main()` — 

## hermes\scripts\v25\v483_two_sided_liquidity_purge_frozen_t1_replay.py
- `f(x)` — 
- `integer(x)` — 
- `ds(x)` — 
- `load(sym)` — 
- `replay(seed, bars)` — 
- `stats(rows)` — 
- `pass_gate(overall, yearly, t1)` — 
- `main()` — 

## hermes\scripts\v25\v484_two_sided_liquidity_purge_direction_closure.py
- `n(x)` — 
- `stats(rows)` — 
- `diff(a, b, fields)` — 
- `main()` — 

## hermes\scripts\v25\v485_bsl_acceptance_retest_generator.py
- `f(x)` — 
- `ds(x)` — 
- `load(path)` — 
- `symbol(path)` — 
- `highs(bars)` — 
- `generate(sym, bars)` — 
- `main()` — 

## hermes\scripts\v25\v486_bsl_acceptance_retest_oracle.py
- `num(x)` — 
- `date(x)` — 
- `read_bars(sym)` — 
- `pivot_highs(bars)` — 
- `derive(sym, bars)` — 
- `main()` — 

## hermes\scripts\v25\v487_bsl_acceptance_retest_frozen_t1_replay.py
- `f(x)` — 
- `integer(x)` — 
- `ds(x)` — 
- `load(sym)` — 
- `replay(seed, bars)` — 
- `stats(rows)` — 
- `pass_gate(overall, yearly, t1)` — 
- `main()` — 

## hermes\scripts\v25\v488_bsl_acceptance_retest_direction_closure.py
- `n(x)` — 
- `stats(rows)` — 
- `diff(a, b, fields)` — 
- `main()` — 

## hermes\scripts\v25\v489_weekly_bos_demand_transfer_generator.py
- `f(x)` — 
- `ds(x)` — 
- `load(path)` — 
- `symbol(path)` — 
- `weeks(daily)` — 
- `weekly_highs(ws)` — 
- `lifecycle(daily, start_date, zl, zh)` — 
- `generate(sym, daily)` — 
- `main()` — 

## hermes\scripts\v25\v490_weekly_bos_demand_transfer_oracle.py
- `num(x)` — 
- `date(x)` — 
- `daily(sym)` — 
- `weekly(ds)` — 
- `check(seed, ds, ws)` — 
- `main()` — 

## hermes\scripts\v25\v491_weekly_bos_demand_transfer_frozen_t1_replay.py
- `f(x)` — 
- `integer(x)` — 
- `ds(x)` — 
- `load(sym)` — 
- `weeks(daily)` — 
- `weekly_targets(daily)` — 
- `target_visible(targets, hold_date, entry)` — 
- `replay(seed, bars, targets)` — 
- `stats(rows)` — 
- `main()` — 

## hermes\scripts\v25\v493_weekly_fvg_demand_transfer_generator.py
- `f(x)` — 
- `ds(x)` — 
- `load(path)` — 
- `symbol(path)` — 
- `weeks(daily)` — 
- `lifecycle(daily, start_date, zl, zh)` — 
- `generate(sym, daily)` — 
- `main()` — 

## hermes\scripts\v25\v494_weekly_fvg_demand_transfer_oracle.py
- `num(x)` — 
- `date(x)` — 
- `daily(sym)` — 
- `weekly(ds)` — 
- `check(seed, ds, ws)` — 
- `main()` — 

## hermes\scripts\v25\v495_weekly_fvg_demand_transfer_frozen_t1_replay.py
- `f(x)` — 
- `integer(x)` — 
- `ds(x)` — 
- `load(sym)` — 
- `weeks(daily)` — 
- `weekly_targets(daily)` — 
- `target_visible(targets, hold_date, entry)` — 
- `replay(seed, bars, targets)` — 
- `stats(rows)` — 
- `main()` — 

## hermes\scripts\v25\v496_weekly_fvg_demand_independent_metric_audit.py
- `stats(rows)` — 
- `main()` — 

## hermes\scripts\v25\v498_weekly_breaker_daily_transfer_generator.py
- `f(x)` — 
- `ds(x)` — 
- `load(path)` — 
- `symbol(path)` — 
- `weeks(daily)` — 
- `confirmed_swing_lows(ws)` — 
- `lifecycle(daily, activation_date, zl, zh)` — 
- `generate(sym, daily)` — 
- `main()` — 

## hermes\scripts\v25\v499_weekly_breaker_daily_transfer_oracle.py
- `num(x)` — 
- `date(x)` — 
- `bars(sym)` — 
- `aggregate(ds)` — 
- `check(s, ds, ws)` — 
- `main()` — 

## hermes\scripts\v25\v500_weekly_breaker_daily_transfer_frozen_t1_replay.py
- `f(x)` — 
- `integer(x)` — 
- `ds(x)` — 
- `load(sym)` — 
- `weeks(daily)` — 
- `weekly_targets(daily)` — 
- `target_visible(targets, hold_date, entry)` — 
- `replay(seed, bars, targets)` — 
- `stats(rows)` — 
- `main()` — 

## hermes\scripts\v25\v501_weekly_breaker_daily_transfer_independent_metric_audit.py
- `stats(rows)` — 
- `main()` — 

## hermes\scripts\v25\v501_weekly_breaker_independent_metric_audit.py
- `stats(rows)` — 
- `main()` — 

## hermes\scripts\v25\v502_weekly_ssl_choch_demand_transfer_generator.py
- `f(x)` — 
- `ds(x)` — 
- `load(path)` — 
- `symbol(path)` — 
- `weeks(daily)` — 
- `pivots(ws, field, greater)` — 
- `lifecycle(daily, choch_date, zl, zh)` — 
- `generate(sym, daily)` — 
- `main()` — 

## hermes\scripts\v25\v503_weekly_ssl_choch_demand_oracle.py
- `num(x)` — 
- `integer(x)` — 
- `date8(x)` — 
- `daily_bars(sym)` — 
- `completed_weeks(bars)` — 
- `is_low(ws, i)` — 
- `is_high(ws, i)` — 
- `first_lifecycle(bars, after, zl, zh)` — 
- `audit(row, bars)` — 
- `main()` — 

## hermes\scripts\v25\v504_weekly_ssl_choch_demand_frozen_t1_replay.py
- `f(x)` — 
- `integer(x)` — 
- `ds(x)` — 
- `load(sym)` — 
- `completed_week_highs(daily)` — 
- `visible_target(targets, hold_date, entry)` — 
- `replay(seed, bars, targets)` — 
- `stats(rows)` — 
- `main()` — 

## hermes\scripts\v25\v505_weekly_ssl_choch_demand_metric_audit.py
- `f(x)` — 
- `stats(rows)` — 
- `same_metrics(a, b)` — 
- `main()` — 

## hermes\scripts\v25\v506_monthly_bos_weekly_fvg_transfer_generator.py
- `f(x)` — 
- `ds(x)` — 
- `load(path)` — 
- `symbol(path)` — 
- `aggregate(daily, key_fn)` — 
- `weeks(daily)` — 
- `months(daily)` — 
- `pivots(rows, field, greater)` — 
- `monthly_regimes(ms)` — 
- `active_regime(events, ms, creation_date)` — 
- `lifecycle(daily, start_date, zl, zh)` — 
- `generate(sym, daily)` — 
- `main()` — 

## hermes\scripts\v25\v507_weekly_ifvg_support_transfer_generator.py
- `f(x)` — 
- `ds(x)` — 
- `load(path)` — 
- `symbol(path)` — 
- `weeks(daily)` — 
- `lifecycle(daily, start_date, zl, zh)` — 
- `generate(sym, daily)` — 
- `main()` — 

## hermes\scripts\v25\v508_weekly_ifvg_support_oracle.py
- `f(x)` — 
- `ds(x)` — 
- `daily(sym)` — 
- `weekly(rows)` — 
- `check(seed, ds_, ws)` — 
- `main()` — 

## hermes\scripts\v25\v509_weekly_ifvg_support_frozen_t1_replay.py
- `f(x)` — 
- `integer(x)` — 
- `ds(x)` — 
- `load(sym)` — 
- `weeks(daily)` — 
- `weekly_targets(daily)` — 
- `target_visible(targets, hold_date, entry)` — 
- `replay(seed, bars, targets)` — 
- `stats(rows)` — 
- `main()` — 

## hermes\scripts\v25\v510_weekly_ifvg_support_metric_audit.py
- `stats(rows)` — 
- `main()` — 

## hermes\scripts\v25\v511_weekly_bos_daily_ssl_reversal_generator.py
- `f(x)` — 
- `ds(x)` — 
- `load(path)` — 
- `symbol(path)` — 
- `weeks(daily)` — 
- `pivots(rows, field, left, right, greater)` — 
- `weekly_bos_contexts(ws)` — 
- `active_context(contexts, date)` — 
- `lifecycle(daily, choch, zl, zh)` — 
- `generate(sym, daily)` — 
- `main()` — 

## hermes\scripts\v25\v512_weekly_bos_daily_ssl_reversal_oracle.py
- `num(x)` — 
- `integer(x)` — 
- `date8(x)` — 
- `bars(sym)` — 
- `completed_weeks(daily)` — 
- `pivot_indices(seq, field, left, right, high)` — 
- `contexts(ws)` — 
- `context_at(items, ws, date)` — 
- `selected_ssl_at(daily, weekly, items, raid)` — 
- `lifecycle(daily, choch, zl, zh)` — 
- `audit(row, daily)` — 
- `main()` — 

## hermes\scripts\v25\v513_weekly_bos_daily_ssl_reversal_frozen_t1_replay.py
- `f(x)` — 
- `integer(x)` — 
- `ds(x)` — 
- `load(sym)` — 
- `completed_week_highs(daily)` — 
- `visible_target(targets, hold_date, entry)` — 
- `replay(seed, bars, targets)` — 
- `stats(rows)` — 
- `main()` — 

## hermes\scripts\v25\v514_weekly_bos_daily_ssl_reversal_metric_audit.py
- `f(x)` — 
- `stats(rows)` — 
- `main()` — 

## hermes\scripts\v25\v515_weekly_two_sided_purge_daily_transfer_generator.py
- `f(x)` — 
- `ds(x)` — 
- `load(path)` — 
- `symbol(path)` — 
- `weeks(daily)` — 
- `pivots(rows, field, left, right, greater)` — 
- `purge_events(ws)` — 
- `lifecycle(daily, choch, zl, zh)` — 
- `generate(sym, daily)` — 
- `main()` — 

## hermes\scripts\v25\v516_local_structure_research_frontier_closure.py
- `read(name)` — 
- `main()` — 

## hermes\scripts\v25\v517_daily_effort_result_absorption_seed_gate.py
- `fnum(v)` — 
- `datekey(v)` — 
- `bars_for(path)` — 
- `is_confirmed_swing_low(bars, j)` — 
- `volume_rank_prior(values, current)` — 
- `canonical_swept_swing_low(bars, sweep_idx, swing_indices)` — Nearest confirmed, still-unmitigated SSL actually swept and reclaimed.
- `scan_symbol(symbol, bars)` — 
- `main()` — 

## hermes\scripts\v25\v517_frontend_adapter.py
- `_load(path, default)` — 
- `_num(value, default)` — 
- `_date(value)` — 
- `artifacts()` — 
- `trades()` — 
- `period_metrics()` — 
- `_year_rows(report)` — 
- `_normalized_yearly(period, replay)` — 
- `_exit_analysis(rows)` — 
- `bundle()` — 
- `_visual_smc_overlay(raw, date_to_idx)` — Display-only Pine-like SMC context. Never contributes a V517 entry or replay row.
- `kline(symbol)` — 
- `add(kind, row, family, price, upper, lower)` — 

## hermes\scripts\v25\v518_daily_effort_result_absorption_independent_oracle.py
- `number(x)` — 
- `day(x)` — 
- `read_bars(p)` — 
- `low_pivot(b, j)` — 
- `canonical_anchor(b, sweep_idx, pivots)` — Independent implementation of the nearest prior confirmed unmitigated SSL.
- `oracle_for(symbol, b)` — 
- `main()` — 

## hermes\scripts\v25\v519_daily_effort_result_absorption_frozen_t1_replay.py
- `num(x)` — 
- `day(x)` — 
- `load_bars(symbol)` — 
- `high_pivot(b, j)` — 
- `visible_target(b, sweep_idx, response_idx, entry)` — 
- `pct(x, base)` — 
- `replay(row, b)` — 
- `stats(rows)` — 
- `monthly_trade_count_gate(rows)` — 
- `main()` — 

## hermes\scripts\v25\v520_daily_effort_result_absorption_independent_metric_audit.py
- `val(x)` — 
- `keydate(x)` — 
- `data(sym)` — 
- `high_confirmed(b, j)` — 
- `prior_target(b, sweep, response, entry)` — 
- `pc(x, b)` — 
- `execute(seed, b)` — 
- `measures(rows)` — 
- `main()` — 
- `compact(r)` — 

## hermes\scripts\v25\v521_daily_effort_result_absorption_scanner_time_dry_run.py
- `n(x)` — 
- `d(x)` — 
- `bars(p)` — 
- `pivot_low(b, j)` — 
- `unmitigated_anchors(b, sweep)` — 
- `canonical_anchor(b, sweep)` — Nearest prior confirmed, unmitigated SSL swept and reclaimed by `sweep`.
- `pivot_high(b, j)` — 
- `target(b, sweep, minimum)` — 
- `candidate(sym, b, market_date)` — 
- `diagnostic_progress(sym, b, market_date)` — Outcome-blind current-date funnel for observability only.
- `main()` — 

## hermes\scripts\v25\v522_effort_result_release_audit.py
- `load(p)` — 
- `main()` — 

## hermes\scripts\v25\v523_effort_result_pending_next_open_shadow.py
- `load(path, default)` — 
- `date_key(value)` — 
- `positive(value)` — 
- `bars(symbol)` — 
- `validate(row, epoch_date)` — 
- `main()` — 

## hermes\scripts\v25\v523_post_close_shadow_observer.py
- `load(path, default)` — 
- `run(command, timeout)` — 
- `save_scheduler_status(status)` — Keep the displayed scheduler state aligned with the actual cron outcome.
- `main()` — 

## hermes\scripts\v25\v524_effort_increment_cost_stress_audit.py
- `positive(x)` — 
- `date_key(x)` — 
- `load_bars(symbol)` — 
- `low_pivot(bars, j)` — 
- `high_pivot(bars, j)` — 
- `rank(prior, current)` — 
- `scan_price_chronology(symbol, bars)` — Outcome-blind superset: V517 price chronology, without its high-volume gate.
- `visible_target(bars, sweep_idx, entry)` — 
- `pct(value, base)` — 
- `execute(seed, bars)` — 
- `measures(rows, cost)` — 
- `band_of(value)` — 
- `serial_replay(seeds)` — 
- `main()` — 

## hermes\scripts\v25\v525_effort_result_structural_rr_gate_audit.py
- `preentry_contract(seed, bars)` — Uses only bars observable at entry open; no exit/outcome fields.
- `main()` — 

## hermes\scripts\v25\v526_v517_live_execution.py
- `load(path, default)` — 
- `save(path, value)` — 
- `sha256_file(path)` — 
- `pending_digest(row)` — 
- `pending_integrity_ok(row)` — 
- `date_key(value)` — 
- `next_weekday(day)` — Calendar lower bound only; exact exchange-session validation is in market_open().
- `record_open_attempt(row, day, quote_date, state)` — 
- `weekday_dates(start, end_exclusive)` — Weekday lower-bound dates between two YYYYMMDD dates.
- `only_confirmed_non_sessions_before(row, expected, today)` — Permit a later weekday only when every earlier weekday was proven closed.
- `quote_prefix(symbol)` — 
- `quote(symbol)` — 
- `research_ready(release)` — 
- `execution_authorization(release)` — Freeze only decision-time license facts onto a current scanner row.
- `pending_is_authorized(row)` — 
- `promote(release)` — 
- `post_close()` — 
- `market_open()` — 
- `monitor()` — 
- `main()` — 

## hermes\scripts\v25\v527_spring_test_effort_result_seed_gate.py
- `number(value)` — 
- `trading_day(value)` — 
- `load_bars(path)` — 
- `confirmed_swing_low(bars, index)` — 
- `top_quintile_volume(bars, index)` — 
- `scan_symbol(symbol, bars)` — 
- `main()` — 

## hermes\scripts\v25\v527_wyckoff_spring_test_sos_seed_gate.py
- `positive(value)` — 
- `day(value)` — 
- `load_bars(path)` — 
- `confirmed_swing_low(bars, index)` — 
- `prior_volume_rank(bars, index)` — 
- `scan_symbol(symbol, bars)` — 
- `main()` — 

## hermes\scripts\v25\v528_spring_test_effort_result_independent_oracle.py
- `f(x)` — 
- `d(x)` — 
- `bars(symbol)` — 
- `pivot_low(b, i)` — 
- `raw_oracle(symbol)` — 
- `main()` — 

## hermes\scripts\v25\v528_wyckoff_spring_test_sos_independent_oracle.py
- `number(value)` — 
- `date_key(value)` — 
- `bars(path)` — 
- `pivot_low(series, at)` — 
- `oracle_rows(symbol, series)` — 
- `main()` — 

## hermes\scripts\v25\v529_spring_test_effort_result_frozen_t1_replay.py
- `num(x)` — 
- `day(x)` — 
- `load(symbol)` — 
- `high_pivot(b, i)` — 
- `target(b, spring, entry)` — 
- `pct(x, b)` — 
- `replay(seed, b)` — 
- `stats(rows)` — 
- `main()` — 

## hermes\scripts\v25\v529_wyckoff_spring_test_sos_frozen_t1_replay.py
- `number(value)` — 
- `day(value)` — 
- `load_bars(symbol)` — 
- `confirmed_high(bars, index)` — 
- `visible_target(bars, sos_index, entry)` — 
- `percent(value, base)` — 
- `replay(seed, bars)` — 
- `measures(rows)` — 
- `main()` — 

## hermes\scripts\v25\v530_sos_backup_effort_result_seed_gate.py
- `positive(value)` — 
- `day(value)` — 
- `bars_for(path)` — 
- `confirmed_high(bars, index)` — 
- `rank_prior(bars, index)` — 
- `scan_symbol(symbol, bars)` — 
- `main()` — 

## hermes\scripts\v25\v531_sos_backup_effort_result_independent_oracle.py
- `n(x)` — 
- `d(x)` — 
- `bars(p)` — 
- `pivot_high(b, i)` — 
- `volrank(b, i)` — 
- `identities(sym, b)` — 
- `main()` — 

## hermes\scripts\v25\v532_sos_backup_effort_result_frozen_t1_replay.py
- `n(x)` — 
- `d(x)` — 
- `load(sym)` — 
- `pivot_high(b, i)` — 
- `target(b, reaccept, entry)` — 
- `pct(value, base)` — 
- `replay(seed, b)` — 
- `metrics(rows)` — 
- `main()` — 

## hermes\scripts\v25\v533_selling_climax_ar_st_sos_seed_gate.py
- `n(x)` — 
- `d(x)` — 
- `load(p)` — 
- `vrank(b, i)` — 
- `scan(sym, b)` — 
- `main()` — 

## hermes\scripts\v25\v534_selling_climax_ar_st_sos_independent_oracle.py
- `n(x)` — 
- `d(x)` — 
- `load(p)` — 
- `rank(b, i)` — 
- `rows(sym, b)` — 
- `main()` — 

## hermes\scripts\v25\v535_selling_climax_ar_st_sos_frozen_t1_replay.py
- `n(x)` — 
- `d(x)` — 
- `load(s)` — 
- `ph(b, i)` — 
- `target(b, sos, e)` — 
- `pct(x, b)` — 
- `replay(x, b)` — 
- `metric(a)` — 
- `main()` — 

## hermes\scripts\v25\v536_build_multitf_raw_cache.py
- `date8(value)` — 
- `atomic_gzip_json(path, payload)` — 
- `atomic_json(path, payload)` — 
- `quarantine(symbol, reason)` — Record a provider-confirmed permanent no-data symbol atomically.
- `universe()` — 
- `path_for(code, exchange, frame)` — 
- `attach_provenance(rows, frame)` — Attach immutable source contract before any provider-derived cache write.
- `query(fields, code, exchange, start, end, frequency)` — 
- `parse_daily(rows)` — 
- `parse_intraday(rows)` — 
- `weekly_from_daily(daily)` — 
- `m60_from_m15(m15)` — Aggregate each four 15m raw bars into the official A-share 60m slots.
- `quarter_chunks()` — 
- `validate_intraday(rows, expected_dates, slots)` — 
- `load_cache(path)` — 
- `build_one(code, exchange)` — 
- `main()` — 

## hermes\scripts\v25\v536_build_sina_partial_multitf_cache.py
- `atomic_gzip(path, rows)` — 
- `atomic_json(path, payload)` — 
- `canonical_universe()` — Use the last dated independent denominator when its live refresh is unavailable.
- `sina_symbol(symbol)` — 
- `fetch(symbol, scale)` — 
- `valid_m15_dates(rows)` — 
- `normalize(rows, frame, requested, received, keep_dates)` — 
- `derived_weekly(daily)` — 
- `derived_m60(m15)` — 
- `build(symbol)` — 
- `main()` — 

## hermes\scripts\v25\v536_cross_source_overlap_audit.py
- `load(path)` — 
- `main()` — 

## hermes\scripts\v25\v536_four_hour_randomized_accelerator.py
- `atomic(payload)` — 
- `atomic_path(path, payload)` — 
- `missing()` — 
- `load_hangs()` — 
- `record_failure(symbol, reason)` — Quarantine a repeatedly non-buildable source response after 3 attempts.
- `clear_hang(symbol)` — 
- `run_one(symbol, timeout_sec)` — 
- `builder_status(symbol)` — 
- `main()` — 

## hermes\scripts\v25\v536_migrate_source_isolated_cache.py
- `load(path)` — 
- `write_gzip(path, rows)` — 
- `source_kind(frame)` — 
- `migrate_rows(rows, frame)` — 
- `output_path(frame, source_file)` — 
- `main()` — 

## hermes\scripts\v25\v536_multitf_cache_batch_controller.py
- `symbols()` — 
- `done()` — 
- `run(cmd, timeout)` — 
- `main()` — 

## hermes\scripts\v25\v536_multitf_cache_integrity_audit.py
- `load(path)` — 
- `slots(rows, expected_days, wanted)` — 
- `audit(symbol)` — 
- `main()` — 

## hermes\scripts\v25\v536_multitf_source_monitor.py
- `save(path, payload)` — 
- `bars_count(frame)` — 
- `bq(freq, fields)` — 
- `sina(frame)` — 
- `tencent_daily()` — 
- `intraday_close_by_time_bao(rows)` — 
- `intraday_close_by_time_sina(rows)` — 
- `compare(bao, sina_rows)` — 
- `main()` — 

## hermes\scripts\v25\v536_research_source_gate.py
- `read(path)` — 
- `main()` — 

## hermes\scripts\v25\v536_sina_cache_completion_controller.py
- `atomic(payload)` — 
- `complete_symbols()` — 
- `run(script)` — 
- `main()` — 

## hermes\scripts\v25\v536_sina_partial_coverage_audit.py
- `symbols(frame)` — 
- `main()` — 

## hermes\scripts\v25\v536_sina_source_probe.py
- `atomic_gzip(path, rows)` — 
- `main()` — 

## hermes\scripts\v25\v536_source_isolated_cache_audit.py
- `load(path)` — 
- `slots(rows, expected, wanted)` — 
- `weekly_from_daily(daily)` — 
- `m60_from_m15(rows)` — 
- `values(rows)` — 
- `ohlcva_equal(left, right)` — Exact timestamp/order, numerically tolerant only for float accumulation noise.
- `audit_symbol(root, symbol)` — 
- `main()` — 

## hermes\scripts\v25\v536a_sina_industry_leadership_seed_gate.py
- `number(value)` — 
- `load_gzip(path)` — 
- `symbol_from_path(path, frame)` — 
- `industry_map()` — 
- `daily_rows(path)` — 
- `swing_low(rows, idx)` — 
- `daily_candidates(symbol, rows)` — 
- `first120_features(symbol, industry, path, wanted)` — 
- `main()` — 

## hermes\scripts\v25\v537_no_supply_compression_expansion_seed_gate.py
- `positive(value)` — 
- `date_key(value)` — 
- `load_bars(path)` — 
- `is_confirmed_swing_low(bars, index)` — 
- `median(values)` — 
- `volume_rank_prior(bars, index)` — 
- `scan_symbol(symbol, bars)` — 
- `main()` — 

## hermes\scripts\v25\v539_sina_m15_ssl_bos_fvg_seed_gate.py
- `num(value)` — 
- `load_rows(path)` — 
- `pivots(rows)` — 
- `symbol_from_path(path)` — 
- `generate(symbol, rows)` — 
- `main()` — 

## hermes\scripts\v25\v540_sina_m15_ssl_bos_fvg_independent_oracle.py
- `positive(value)` — 
- `bars(path)` — 
- `swing_flags(rows)` — 
- `derive(symbol, rows)` — 
- `tuple_of(row)` — 
- `frozen_rows()` — 
- `main()` — 

## hermes\scripts\v25\v541_sina_m15_ssl_bos_fvg_frozen_t1_replay.py
- `positive(value)` — 
- `load_bars(symbol)` — 
- `high_pivots(rows)` — 
- `pct(value, base)` — 
- `range_max(table, left, right)` — Inclusive O(1) max query over a precomputed sparse table.
- `high_table(rows)` — 
- `target_cache(rows, pivots, index, seeds, highs)` — Resolve all frozen target queries in one forward O(n log n) pass.
- `replay(seed, rows, index, target_choice)` — 
- `stats(rows)` — 
- `main()` — 

## hermes\scripts\v25\v542_sina_m15_v541_failure_attribution.py
- `number(value)` — 
- `stamp(value)` — 
- `metric(rows)` — 
- `interval_hours(row, start, end)` — 
- `binned(rows, name, key)` — 
- `quantile_bucket(value, cuts, labels)` — 
- `main()` — 

## hermes\scripts\v25\v543_sina_m15_seed_merge.py
- `main()` — 

## hermes\scripts\v25\v543_sina_m15_seed_shard.py
- `main()` — 

## hermes\scripts\v25\v543_sina_m15_ssl_displacement_absorption_seed_gate.py
- `num(value)` — 
- `load_rows(path)` — 
- `pivots(rows)` — 
- `baseline(rows, i)` — 
- `symbol(path)` — 
- `generate(ticker, rows)` — 
- `main()` — 

## hermes\scripts\v25\v544_sina_m15_ssl_displacement_absorption_independent_oracle.py
- `number(value)` — 
- `read_bars(path)` — 
- `swing_flags(rows)` — 
- `local_reference(rows, i)` — 
- `derive(symbol, rows)` — 
- `tuple_of(row)` — 
- `run_shard(index, total)` — 
- `merge(total)` — 
- `main()` — 

## hermes\scripts\v25\v545_sina_m15_ssl_displacement_absorption_frozen_t1_replay.py
- `main()` — 

## hermes\scripts\v25\v546_sina_m15_v545_failure_attribution.py
- `value(row, name)` — 
- `metrics(rows)` — 
- `bucket(rows, key)` — 
- `band(x, cuts, names)` — 
- `main()` — 

## hermes\scripts\v25\v547_local_smc_frontier_reconciliation.py
- `load(key)` — 
- `main()` — 

## hermes\scripts\v25\v548_htf_trend_m15_entry_seed_gate.py
- `number(value)` — 
- `read_gzip(path, frame)` — 
- `pivots(rows)` — 
- `completed_weeks(daily)` — 
- `trend_state(rows, lows, highs, asof)` — Resolve a trend from pivots whose right-side confirmation is pre-entry.
- `rolling_baseline(rows, index)` — 
- `m15_entries(symbol, rows, weekly, daily)` — 
- `process_symbol(m15_path)` — 
- `main()` — 

## hermes\scripts\v25\v550_htf_m15_independent_oracle.py
- `f(x)` — 
- `bars(path, m15)` — 
- `pivot(rows)` — 
- `completed_weekly(daily)` — 
- `uptrend(rows, lo, hi, before)` — 
- `base(rows, i)` — 
- `derive(path)` — 
- `tup(r)` — 
- `main()` — 

## hermes\scripts\v25\v551_htf_m15_exploratory_frozen_t1_replay.py
- `positive(value)` — 
- `load_bars(symbol)` — 
- `high_pivots(rows)` — 
- `pct(value, base)` — 
- `range_max(table, left, right)` — Inclusive O(1) max query over a precomputed sparse table.
- `high_table(rows)` — 
- `target_cache(rows, pivots, index, seeds, highs)` — Resolve all frozen target queries in one forward O(n log n) pass.
- `replay(seed, rows, index, target_choice)` — 
- `stats(rows)` — 
- `main()` — 

## hermes\scripts\v25\v552_research_frontier_final_reconciliation.py
- `read_json(name)` — 
- `main()` — 

## hermes\scripts\v25\v553_daily_candidate_mtf_lineage_audit.py
- `positive(value)` — 
- `load(path, frame)` — 
- `old_selected_keys()` — Read only identity columns; never load old outcome columns.
- `m15_label(rows, zone_low, zone_high)` — Classify same-session evidence without using bars after daily reclaim day.
- `scan_symbol(path, old_keys)` — 
- `main()` — 

## hermes\scripts\v25\v554_daily_m15_takeover_independent_oracle.py
- `val(x)` — 
- `rows(p, minute)` — 
- `takeover(xs, lo, hi)` — 
- `scan(p)` — 
- `source_ids(path)` — 
- `main()` — 

## hermes\scripts\v25\v555_daily_m15_takeover_frozen_t1_diagnostic.py
- `n(x)` — 
- `bars(sym)` — 
- `target(xs, ei, entry, stop)` — 
- `metric(rows)` — 
- `main()` — 

## hermes\scripts\v25\v556_v555_sl_mechanism_attribution.py
- `num(value)` — 
- `load(path, frame)` — 
- `confirmed_swing_high(rows, index, right_end)` — 
- `target_anchor(rows, entry_i, target)` — Locate V555's already-frozen target without recomputing its selector.
- `stat(rows)` — 
- `main()` — 

## hermes\scripts\v25\v557_daily_demand_confirmed_m15_choch_seed.py
- `num(x)` — 
- `bars(sym)` — 
- `swing_high(xs, i)` — 
- `index_symbol(sym)` — 
- `classify(state, c)` — 
- `main()` — 

## hermes\scripts\v25\v558_v557_independent_raw_oracle.py
- `n(x)` — 
- `load(sym)` — 
- `peak(xs, i)` — 
- `accept(xs, ix, c)` — 
- `main()` — 

## hermes\scripts\v25\v559_confirmed_m15_choch_frozen_t1_replay.py
- `n(x)` — 
- `load(sym)` — 
- `peak(xs, i)` — 
- `target(xs, ei, entry, stop)` — 
- `metrics(rows)` — 
- `main()` — 

## hermes\scripts\v25\v561_current_intraday_source_requalification.py
- `sina_symbol(symbol)` — 
- `date_range(rows)` — 
- `sina_probe(session, symbol)` — 
- `tencent_probe(session, symbol)` — 
- `qualified(rows)` — 
- `main()` — 

## hermes\scripts\v25\v561_multilane_source_qualification.py
- `probe_sse_margin(date)` — 
- `probe_szse_margin(date)` — 
- `probe_northbound(date)` — 
- `probe_tick()` — 
- `pass_all(rows, flag, min_rows)` — 
- `main()` — 

## hermes\scripts\v25\v562_exchange_margin_raw_builder.py
- `trading_dates()` — 
- `sse(date)` — 
- `szse(date)` — 
- `output(exchange, date)` — 
- `valid(path, date, exchange)` — 
- `store(exchange, date, rows)` — 
- `main()` — 
- `num(x)` — 

## hermes\scripts\v25\v562_htf_industry_m15_absorption_seed_gate.py
- `positive(value)` — 
- `load_gzip(path)` — 
- `daily_rows(symbol)` — 
- `pivots(rows)` — 
- `completed_weeks(daily)` — 
- `completed_higher_low(rows, asof)` — 
- `industry_map()` — 
- `first120(symbol, wanted)` — 
- `next_trade_day(dates, date)` — 
- `main()` — 

## hermes\scripts\v25\v562_industry_bos_m15_ssl_choch_seed.py
- `f(x)` — 
- `daily_bars(sym)` — 
- `m15_bars(sym)` — 
- `swing_high(xs, i)` — 
- `swing_low(xs, i)` — 
- `build_industry_source()` — 
- `ex_stock_industry(sym, ind, sums, own)` — 
- `industry_bos_by_date(xs)` — 
- `stock_m15_event(session)` — 
- `main()` — 

## hermes\scripts\v25\v562_industry_synchronized_m15_takeover_seed.py
- `positive(x)` — 
- `load_industry()` — 
- `symbol_from_path(path)` — 
- `read_seed_rows()` — 
- `slot_for_timestamp(raw)` — Return Sina's actual A-share 15m closing-bar slot (09:45..11:30, 13:15..15:00).
- `exact_slot(seed)` — 
- `build_requests(seeds)` — 
- `bars_for_needed_dates(path, needed)` — 
- `build_cross_sectional(industry_map, needed)` — 
- `main()` — 

## hermes\scripts\v25\v562_margin_build_watchdog.py

## hermes\scripts\v25\v562_pit_event_archive_source_pilot.py
- `prefix(symbol)` — 
- `symbols_by_stratum()` — 
- `event_type(title)` — 
- `fetch_symbol(symbol)` — 
- `main()` — 

## hermes\scripts\v25\v562_ssl_industry_midday_transmission_seed.py
- `positive(value)` — 
- `load(path)` — 
- `symbol_from(path, frame)` — 
- `industry_map()` — 
- `daily(path)` — 
- `confirmed_swing_low(rows, index)` — 
- `daily_ssl_seeds(symbol, rows)` — All information here is fixed by each sweep-day close.
- `first120(path, wanted, symbol, industry)` — 
- `main()` — 

## hermes\scripts\v25\v562_v300_candidate_identity_audit.py
- `f(x, default)` — 
- `is_v300_published_rule(r)` — 
- `raw_metrics(rows)` — 
- `dedupe(rows, key, chooser)` — 
- `summarize_scope(name, rows)` — 
- `main()` — 
- `stat(vals)` — 

## hermes\scripts\v25\v563_industry_bos_opening_liquidity_seed.py
- `opening_acceptance(session)` — 
- `main()` — 

## hermes\scripts\v25\v563_industry_led_m60_external_sweep_choch_seed.py
- `sf(x, default)` — 
- `day(x)` — 
- `load(p)` — 
- `sym_from_path(p)` — 
- `daily_path(sym)` — 
- `build_industry_context(industry)` — Return (previous_day, industry)->activation from strictly completed daily bars.
- `confirmed_swing_high(bars, before)` — Latest 2L/2R high whose right confirmation finishes before `before`.
- `seeds_for_symbol(sym, ind, active, prev_day)` — 
- `main()` — 

## hermes\scripts\v25\v563_industry_synchronized_m15_independent_oracle.py
- `fnum(value)` — 
- `session_slot(timestamp)` — 
- `load_mapping()` — 
- `source_seeds()` — 
- `path_symbol(path)` — 
- `read_needed(path, needed_by_date)` — date -> [(actual slot, first-available session open, close, cumulative amount)].
- `build_oracle_features(mapping, needed_by_date)` — 
- `canonical(rows)` — 
- `main()` — 

## hermes\scripts\v25\v563_pit_event_archive_full_coverage_no_outcome.py
- `kind_of(title)` — 
- `fetch(symbol)` — 
- `main()` — 

## hermes\scripts\v25\v563_ssl_industry_expansion_midday_seed.py
- `no_volume_ssl_seeds(symbol, rows)` — A confirmed external SSL raid/reclaim; daily volume is descriptive only.
- `main()` — 

## hermes\scripts\v25\v564_daily_hl_opening_range_ssl_acceptance_seed.py
- `number(value)` — 
- `load(path)` — 
- `daily_bars(symbol)` — 
- `m15_by_day(symbol)` — 
- `confirmed_lows(rows)` — 
- `parent_by_date(rows)` — 
- `opening_range_event(bars)` — 
- `main()` — 

## hermes\scripts\v25\v564_industry_led_m60_external_sweep_choch_oracle.py
- `f(x, d)` — 
- `dn(x)` — 
- `load(p)` — 
- `sym(p)` — 
- `dp(s)` — 
- `activation(indmap)` — 
- `verify(r, active, prior)` — 
- `main()` — 

## hermes\scripts\v25\v564_industry_synchronized_m15_frozen_t1_replay.py
- `num(value)` — 
- `daily_bars(symbol)` — 
- `swing_high(rows, index)` — 
- `structural_target(rows, entry_index, entry, stop)` — 
- `metrics(rows)` — 
- `gate(overall, yearly, violations)` — 
- `main()` — 

## hermes\scripts\v25\v564_v563_independent_raw_oracle.py
- `n(value)` — 
- `unpack(path)` — 
- `name(path, frame)` — 
- `daily_bars(path)` — 
- `pivot_low(rows, p)` — 
- `rebuild_daily(path)` — 
- `session_features(path, wanted, industry)` — 
- `main()` — 

## hermes\scripts\v25\v565_daily_hl_prior_ssl_m15_lh_transfer_seed.py
- `f(x)` — 
- `load(path)` — 
- `daily(sym)` — 
- `sessions(sym)` — 
- `daily_hl_parent(xs)` — 
- `m15_event(xs, prior_low)` — 
- `main()` — 

## hermes\scripts\v25\v565_industry_led_m60_external_sweep_choch_frozen_replay.py
- `f(x, d)` — 
- `dn(x)` — 
- `load(p)` — 
- `dp(s)` — 
- `swing_highs(bars, event_i)` — 
- `replay(r, cache)` — 
- `metrics(rows)` — 
- `main()` — 
- `st(x)` — 

## hermes\scripts\v25\v565_industry_synchronized_m15_metric_audit.py
- `summarize(rows)` — 
- `main()` — 

## hermes\scripts\v25\v565_pit_commitment_smc_response_seed.py
- `f(x)` — 
- `selected_family(row)` — 
- `load_events()` — 
- `load_bars(symbol)` — 
- `pivot_low(xs, i)` — 
- `pivot_high(xs, i)` — 
- `find_first_chain(event, xs)` — 
- `main()` — 

## hermes\scripts\v25\v565_v563_frozen_t1_replay.py
- `n(x)` — 
- `bars(sym)` — 
- `high(x, i)` — 
- `target(x, ei, entry, stop)` — 
- `metric(rows)` — 
- `main()` — 

## hermes\scripts\v25\v565_v563_preentry_target_feasibility.py
- `number(value)` — 
- `bars(symbol)` — 
- `swing_high(rows, index)` — 
- `feasible(seed, rows)` — 
- `main()` — 

## hermes\scripts\v25\v566_daily_hl_opening_bsl_acceptance_retest_seed.py
- `f(x)` — 
- `load(p)` — 
- `daily(sym)` — 
- `sessions(sym)` — 
- `parent(xs)` — 
- `event(xs)` — 
- `main()` — 

## hermes\scripts\v25\v566_industry_activation_m60_micro_continuation_seed.py
- `f(x, d)` — 
- `dn(x)` — 
- `load(p)` — 
- `sym(p)` — 
- `dp(s)` — 
- `daily_context(ind)` — 
- `main()` — 

## hermes\scripts\v25\v566_v563_frozen_t1_replay.py
- `number(value)` — 
- `daily(symbol)` — 
- `replay(seed, rows)` — 
- `metrics(rows)` — 
- `main()` — 

## hermes\scripts\v25\v567_pit_commitment_structural_execution_seed.py
- `num(x)` — 
- `family(r)` — 
- `events()` — 
- `bars(sym)` — 
- `plow(xs, i)` — 
- `phigh(xs, i)` — 
- `anchor_seed(ev, xs)` — 
- `main()` — 

## hermes\scripts\v25\v567_v566_independent_identity_oracle.py
- `val(x)` — 
- `raw(path)` — 
- `dload(sym)` — 
- `iload(sym)` — 
- `parent_dates(ds)` — 
- `m15_signal(b)` — 
- `main()` — 

## hermes\scripts\v25\v568_v566_frozen_strict_t1_replay.py
- `f(x)` — 
- `bars(sym)` — 
- `confirmed_highs(xs)` — 
- `target_for(xs, signal_i, entry, stop)` — 
- `close_trade(xs, entry_i, entry, stop, target)` — 
- `metrics(rows)` — 
- `main()` — 

## hermes\scripts\v25\v569_margin_commitment_smc_response_seed.py
- `number(value)` — 
- `load_margin(exchange, date)` — 
- `margin_impulses()` — Return transition-into-high commitment events; all ranks are source-only.
- `daily(symbol)` — 
- `pivots(rows)` — 
- `first_chain(event, rows, lows, highs)` — 
- `main()` — 

## hermes\scripts\v25\v570_v569_independent_raw_oracle.py
- `n(x)` — 
- `doc(ex, date)` — 
- `margin_events()` — Reconstruct eligible external events independently from provider records.
- `bars(sym)` — 
- `piv(xs)` — 
- `identity_for(sym, mdate, xs, lo, hi)` — 
- `main()` — 

## hermes\scripts\v25\v571_v569_frozen_strict_t1_replay.py
- `n(x)` — 
- `bars(sym)` — 
- `highs(xs)` — 
- `target(xs, signal_i, entry, stop)` — 
- `exit_trade(xs, entry_i, entry, stop, tp)` — 
- `metrics(rows)` — 
- `main()` — 

## hermes\scripts\v25\v572_v566_industry_activation_independent_oracle.py
- `num(value)` — 
- `date_of(value)` — 
- `symbol_from_file(path)` — 
- `read_list(path)` — 
- `read_industry()` — 
- `daily_activation(industry)` — Rebuild previous-session sector activation directly from daily raw bars.
- `m60_snapshot(industry)` — Build first/second 60m observations, independently of the V566 generator.
- `industry_leaders(industry, snapshots)` — 
- `actual_identities()` — 
- `expected_identities()` — 
- `main()` — 

## hermes\scripts\v25\v573_v566_industry_activation_frozen_t1_replay.py
- `num(value)` — 
- `date_of(value)` — 
- `daily_bars(symbol)` — 
- `confirmed_highs(rows, event_index)` — Only 3L/3R daily highs whose right confirmation completed before event day.
- `target_for(rows, event_index, entry, stop)` — 
- `replay(seed_rows)` — 
- `metrics(rows)` — 
- `main()` — 

## hermes\scripts\v25\v574_v573_independent_metric_audit.py
- `metrics(rows)` — 

## hermes\scripts\v25\v577_lending_short_pressure_smc_squeeze_seed.py
- `positive(value)` — 
- `load_margin(exchange, date)` — 
- `lending_pressure_events()` — Build cross-sectional source-only transitions into high short pressure.
- `daily_bars(symbol)` — 
- `confirmed_highs(rows)` — 
- `first_response(event, rows, highs)` — 
- `main()` — 

## hermes\scripts\v25\v578_v577_independent_raw_oracle.py
- `num(value)` — 
- `source_rows(exchange, date)` — 
- `external_event_dates()` — Independently reconstruct q75 lending-pressure state transitions.
- `bars(symbol)` — 
- `confirmed_highs(rows)` — 
- `identity(symbol, event_date, rows, highs)` — 
- `main()` — 

## hermes\scripts\v25\v579_v577_frozen_strict_t1_replay.py
- `num(value)` — 
- `bars(symbol)` — 
- `confirmed_highs(rows)` — 
- `structural_target(rows, signal_i, entry, stop)` — 
- `exit_trade(rows, entry_i, entry, stop, target)` — 
- `metrics(rows)` — 
- `main()` — 

## hermes\scripts\v25\v582_lockup_release_ssl_exhaustion_seed.py
- `positive(value)` — 
- `date8(value)` — 
- `lockup_events()` — Source-only event extractor; title rule is frozen in V581.
- `daily_bars(symbol)` — 
- `confirmed_swings(rows)` — 3L/3R pivots; confirmation index encodes information availability.
- `first_response(event, rows)` — 
- `main()` — 

## hermes\scripts\v25\v585_insider_reduction_plan_ssl_exhaustion_seed.py
- `events()` — 
- `main()` — 

## hermes\scripts\v25\v586_v585_independent_raw_oracle.py
- `d8(x)` — 
- `pos(x)` — 
- `raw_events()` — 
- `bars(symbol)` — 
- `pivots(xs)` — 
- `rebuild(symbol, event_date, xs)` — 
- `main()` — 

## hermes\scripts\v25\v587_v585_frozen_strict_t1_replay.py
- `main()` — 

## hermes\scripts\v25\v589_buyback_commitment_demand_retest_preregistration.py
- `main()` — 

## hermes\scripts\v25\v590_buyback_commitment_demand_retest_seed.py
- `d8(value)` — 
- `positive(value)` — 
- `events()` — 
- `bars(symbol)` — 
- `confirmed_highs(rows)` — 
- `first_response(event, rows)` — 
- `main()` — 

## hermes\scripts\v25\v591_earnings_attention_volume_fvg_preregistration.py
- `main()` — 

## hermes\scripts\v25\v592_earnings_attention_volume_fvg_seed.py
- `d8(value)` — 
- `positive(value)` — 
- `events()` — 
- `bars(symbol)` — 
- `confirmed_highs(rows)` — 
- `first_response(event, rows)` — 
- `main()` — 

## hermes\scripts\v25\v594_holder_demand_commitment_preregistration.py
- `main()` — 

## hermes\scripts\v25\v595_holder_demand_commitment_seed.py
- `d8(value)` — 
- `positive(value)` — 
- `events()` — 
- `bars(symbol)` — 
- `confirmed_highs(rows)` — 
- `first_response(event, rows)` — 
- `main()` — 

## hermes\scripts\v25\v596_contract_award_event_catalog.py
- `days()` — 
- `fetch_one(day)` — 
- `load_state()` — 
- `write_state(state)` — 
- `main()` — 

## hermes\scripts\v25\v597_contract_award_demand_retest_preregistration.py
- `main()` — 

## hermes\scripts\v25\v598_contract_award_demand_retest_seed.py
- `d8(value)` — 
- `positive(value)` — 
- `events(catalog)` — 
- `bars(symbol)` — 
- `confirmed_highs(rows, end)` — 
- `first_response(event, rows)` — 
- `main()` — 

## hermes\scripts\v25\v599_v598_independent_raw_oracle.py
- `date8(value)` — 
- `number(value)` — 
- `event_dates(catalog)` — 
- `daily(symbol)` — 
- `exact_identity(symbol, event_day, rows)` — 
- `main()` — 

## hermes\scripts\v25\v600_v598_frozen_strict_t1_replay.py
- `main()` — 

## hermes\scripts\v25\v601_current_available_data_strategy_frontier_reconciliation.py
- `load(name)` — 
- `main()` — 

## hermes\scripts\v25\v601_current_qualified_strategy_frontier.py
- `load(name)` — 
- `main()` — 

## hermes\scripts\v25\v602_canonical_bos_demand_reclaim_seed.py
- `number(value)` — 
- `date8(value)` — 
- `symbol(path)` — 
- `load(path)` — 
- `confirmed_highs(rows)` — 
- `nearest_bearish_ob(rows, break_i)` — 
- `lifecycle(rows, start_i, zone_low, zone_high)` — 
- `generate(sym, rows)` — 
- `main()` — 

## hermes\scripts\v25\v602_margin_source_and_ontology_reconciliation.py
- `audit_exchange(exchange)` — 
- `main()` — 

## hermes\scripts\v25\v602_v539_smc_semantic_lifecycle_audit.py
- `load_bars(symbol)` — 
- `pct(n, d)` — 
- `main()` — 

## hermes\scripts\v25\v603_equity_incentive_event_catalog.py
- `calendar_days()` — 
- `classify(title)` — 
- `fetch_one(day)` — 
- `load_state()` — 
- `main()` — 

## hermes\scripts\v25\v603_reversal_ssl_choch_displacement_state_machine.py
- `positive(value)` — 
- `load_rows(path)` — 
- `pivots(rows)` — 
- `empty_chain(symbol, pivot_i, pivot_confirm_i, high_i, rows, sweep_i)` — 
- `terminal(chain, status, at, reason)` — 
- `causal_ob(rows, start_i, choch_i)` — Last bearish candle strictly before the CHOCH break bar, within the leg.
- `is_displacement_bar(bar)` — 
- `first_causal_fvg(rows, chain, i)` — FVG must be created by the post-sweep displacement leg, never pre-event.
- `public_row(chain, rows)` — 
- `emit_terminal(chain, rows, records)` — 
- `generate(symbol, rows)` — 
- `symbol_from_path(path)` — 
- `process_path(path_text)` — Independent source-local symbol scan; suitable for process workers.
- `write_csv(path, rows)` — 
- `main()` — 
- `ordered(row)` — 

## hermes\scripts\v25\v603_reversal_state_machine.py
- `positive(value)` — 
- `load_rows(path)` — 
- `pivots(rows)` — 
- `symbol_from_path(path)` — 
- `base_record(symbol, state, terminal, reason)` — 
- `body_ratio(bar)` — 
- `causal_ob(rows, state, fvg_i)` — 
- `generate(symbol, rows)` — 
- `validate(records)` — 
- `main()` — 
- `before(row, left, right)` — 

## hermes\scripts\v25\v603_ssl_choch_displacement_pristine_state_machine.py
- `num(value)` — 
- `load_rows(path)` — 
- `pivots(rows)` — 
- `symbol_from_path(path)` — 
- `blank_record(symbol, state, status, reason)` — 
- `causal_ob(rows, state, displacement_i)` — 
- `is_displacement_fvg(rows, state, i)` — 
- `make_sweep_state(rows, pivot_i, reference_high_i, sweep_i)` — 
- `generate(symbol, rows)` — 
- `validate(records)` — 
- `main()` — 

## hermes\scripts\v25\v604_equity_incentive_demand_retest_preregistration.py
- `main()` — 

## hermes\scripts\v25\v604_export_v603_manual_chain_windows.py
- `bars(symbol)` — 
- `read(path)` — 

## hermes\scripts\v25\v604_v603_independent_raw_bar_oracle.py
- `bars_for(symbol)` — 
- `is_low_pivot(bars, i)` — 
- `is_high_pivot(bars, i)` — 
- `touch(bar, low, high)` — 
- `check_common(row, bars, ix)` — 
- `check_complete_path(row, bars, ix)` — 
- `check_terminal(row, bars, ix)` — 
- `main()` — 

## hermes\scripts\v25\v604_v603_independent_semantic_audit.py
- `load_bars(symbol)` — 
- `first_intersection(bars, start, end, low, high)` — 
- `pick_samples(rows, count)` — 
- `window(row, bars)` — 
- `audit_symbol(task)` — Independent per-symbol lifecycle reconstruction; safe for process pool.
- `main()` — 

## hermes\scripts\v25\v605_equity_incentive_demand_retest_seed.py
- `d8(value)` — 
- `positive(value)` — 
- `event_rows(catalog)` — 
- `bars(symbol)` — 
- `confirmed_highs(rows, end)` — 
- `seed_for(event, rows)` — 
- `main()` — 

## hermes\scripts\v25\v605_render_v603_manual_samples.py
- `render(name, samples)` — 
- `main()` — 

## hermes\scripts\v25\v605_v602_frozen_strict_t1_replay.py
- `require_authorization()` — 
- `main()` — 

## hermes\scripts\v25\v605_v603_stage2_three_chain_visual_audit.py
- `load_bars(symbol)` — 
- `main()` — 

## hermes\scripts\v25\v606_v602_independent_metric_audit_and_closure.py
- `calc(rows)` — 
- `main()` — 

## hermes\scripts\v25\v606_v605_independent_raw_oracle.py
- `date8(value)` — 
- `number(value)` — 
- `source_events(catalog)` — 
- `daily(symbol)` — 
- `identity(symbol, event_day, rows)` — 
- `main()` — 

## hermes\scripts\v25\v607_v603_manual_chain_chart_export.py
- `esc(value)` — 
- `render(group, samples)` — 
- `main()` — 

## hermes\scripts\v25\v607_v605_frozen_strict_t1_replay.py
- `main()` — 

## hermes\scripts\v25\v608_equity_incentive_pit_source_catalog.py
- `universe()` — 
- `date8(value)` — 
- `eligible(title)` — 
- `fetch(symbol)` — 
- `main()` — 

## hermes\scripts\v25\v609_cash_dividend_plan_event_catalog.py
- `days()` — 
- `matched(title)` — 
- `fetch(day)` — 
- `main()` — 

## hermes\scripts\v25\v609_controlling_holder_pledge_pit_source_catalog.py
- `universe()` — 
- `date8(value)` — 
- `event_kind(title)` — 
- `fetch(symbol)` — 
- `main()` — 

## hermes\scripts\v25\v609_v603_full_raw_semantic_witness.py
- `load_bars(symbol)` — 
- `pivot_sets(bars)` — 
- `ratio(bar)` — 
- `num(row, key)` — 
- `check_valid(row, bars, ix, low_pivots, high_pivots)` — 
- `check_terminal(row, bars, ix)` — Audit the two L3 rejection states against their first touch alone.
- `audit_symbol(task)` — 
- `main()` — 

## hermes\scripts\v25\v610_profit_distribution_demand_retest_preregistration.py
- `main()` — 

## hermes\scripts\v25\v611_profit_distribution_demand_retest_seed.py
- `d8(value)` — 
- `positive(value)` — 
- `a_share(symbol)` — 
- `event_rows(catalog)` — 
- `bars(symbol)` — 
- `confirmed_highs(rows, end)` — 
- `seed_for(event, rows)` — 
- `main()` — 

## hermes\scripts\v25\v612_v603_frozen_strict_t1_replay.py
- `f(v)` — 
- `load(symbol)` — 
- `highs(rows)` — 
- `target_at_entry(rows, entry_i, price)` — Nearest prior right-confirmed high still unconsumed at the entry bar.
- `run_seed(seed, rows)` — 
- `main()` — 

## hermes\scripts\v25\v612_v611_independent_raw_oracle.py
- `d8(value)` — 
- `positive(value)` — 
- `a_share(symbol)` — 
- `source_events(catalog)` — 
- `daily(symbol)` — 
- `identity(symbol, event_day, rows)` — 
- `main()` — 

## hermes\scripts\v25\v613_v611_frozen_strict_t1_replay.py
- `main()` — 

## hermes\scripts\v25\v614_v611_independent_metric_audit_and_closure.py
- `calc(rows)` — 
- `main()` — 

## hermes\scripts\v25\v615_controlling_pledge_pit_event_catalog.py
- `calendar_days()` — 
- `normalize_date(value)` — 
- `event_kind(title)` — 
- `symbol_for(item)` — 
- `fetch_day(day)` — 
- `load_state()` — 
- `main()` — 

## hermes\scripts\v25\v616_controlling_pledge_release_demand_retest_preregistration.py
- `main()` — 

## hermes\scripts\v25\v617_controlling_pledge_release_demand_retest_seed.py
- `d8(value)` — 
- `positive(value)` — 
- `a_share(symbol)` — 
- `event_rows(catalog)` — 
- `bars(symbol)` — 
- `confirmed_highs(rows, end)` — 
- `seed_for(event, rows)` — 
- `main()` — 

## hermes\scripts\v25\v618_v617_independent_raw_oracle.py
- `d8(value)` — 
- `positive(value)` — 
- `a_share(symbol)` — 
- `source_events(catalog)` — 
- `daily(symbol)` — 
- `identity(symbol, event_day, rows)` — 
- `main()` — 

## hermes\scripts\v25\v619_v617_frozen_strict_t1_replay.py
- `main()` — 

## hermes\scripts\v25\v620_v617_independent_metric_audit_and_closure.py
- `calc(rows)` — 
- `main()` — 

## hermes\scripts\v25\v622_pledge_creation_ssl_exhaustion_seed.py
- `d8(value)` — 
- `positive(value)` — 
- `a_share(symbol)` — 
- `event_rows(catalog)` — 
- `bars(symbol)` — 
- `confirmed_lows(rows, end)` — 
- `confirmed_lower_highs(rows, end)` — 
- `seed_for(event, rows)` — 
- `main()` — 

## hermes\scripts\v25\v622_v606_frozen_strict_t1_replay.py
- `positive(value)` — 
- `load(symbol)` — 
- `confirmed_highs_before(rows, end_i)` — Return only 3L/3R highs fully confirmed before the entry bar.
- `structural_target(rows, entry_i, entry_open)` — 
- `replay_seed(seed, rows, fee_pct)` — 
- `main()` — 

## hermes\scripts\v25\v623_v622_independent_raw_oracle.py
- `clean_date(value)` — 
- `number(value)` — 
- `equity(symbol)` — 
- `load_events(catalog)` — 
- `load_bars(symbol)` — 
- `pivots(rows)` — 
- `reconstruct(event, rows)` — 
- `identity(row)` — 
- `main()` — 

## hermes\scripts\v25\v624_v622_frozen_strict_t1_replay.py
- `main()` — 

## hermes\scripts\v25\v625_v606_independent_replay_audit.py
- `load(symbol)` — 
- `target(rows, entry_i, entry_price)` — 
- `expected_exit(rows, entry_i, stop, take)` — 
- `close(audit, reason)` — 
- `main()` — 

## hermes\scripts\v25\v625_v622_independent_metric_audit_and_closure.py
- `calc(rows)` — 
- `main()` — 

## hermes\scripts\v25\v627_earnings_payload_pit_source_pilot.py
- `declared_direction(content)` — Only accept the notice's explicit current-period direction sentence.
- `sample(events, year)` — 
- `fetch(event)` — 
- `main()` — 

## hermes\scripts\v25\v628_earnings_payload_build_watchdog.py

## hermes\scripts\v25\v628_earnings_payload_raw_builder.py
- `events()` — 
- `path(event)` — 
- `failure_path(event)` — 
- `valid(event)` — 
- `terminal_failure(event)` — 
- `fetch(event)` — 
- `store(event, doc)` — 
- `store_failure(event, error)` — 
- `main()` — 

## hermes\scripts\v25\v632_positive_earnings_preannouncement_semantic_catalog.py
- `documents()` — 
- `main()` — 

## hermes\scripts\v25\v634_earnings_payload_semantic_primitive_census.py
- `documents()` — 
- `main()` — 

## hermes\scripts\v25\v636_current_forecast_turnaround_semantic_catalog.py
- `docs()` — 
- `normalized(doc)` — 
- `primary(doc)` — Bounded-section parser: required headings then exact phrase before next section.
- `oracle(doc)` — Independent regex: required headings and phrase in non-greedy situation span.
- `canonical(rows)` — 
- `main()` — 

## hermes\scripts\v25\v640_turnaround_post_disclosure_outcome_blind_seed.py
- `sym_path(symbol)` — 
- `bars(symbol)` — 
- `close_after_publication(rows, publication_time)` — 
- `confirmed_highs(rows, available_through)` — 
- `target(rows, hold, entry, entry_open)` — 
- `invalid(row, reason)` — 
- `one_event(event, rows, start, boundary)` — Build one causal chain using only rows up to its planned entry open.
- `main()` — 

## hermes\scripts\v25\v640_turnaround_post_disclosure_seed.py
- `day8(value)` — 
- `clock(value)` — 
- `number(value)` — 
- `load_bars(symbol)` — 
- `observation_index(bars, publication_time)` — 
- `pivot_highs(bars, e0)` — 
- `response_break(bars, e0, pivots)` — 
- `origin_ob(bars, e0, e1)` — 
- `lifecycle(bars, e1, origin)` — 
- `candidate(event, bars)` — 
- `cancel_overlaps(records)` — 
- `main()` — 

## hermes\scripts\v25\v641_turnaround_post_disclosure_independent_oracle.py
- `load(symbol)` — 
- `observed_at(data, published)` — 
- `high_pivots(data, known)` — 
- `unbroken(data, pivot, through)` — 
- `desired_target(data, hold, entry)` — 
- `scan(event, data, first, cutoff)` — 
- `key(row)` — 
- `main()` — 

## hermes\scripts\v25\v643_cash_distribution_terms_raw_builder.py
- `denominator()` — 
- `output(event)` — 
- `failure(event)` — 
- `good(event)` — 
- `fetch(event)` — 
- `save(path, body)` — 
- `main()` — 

## hermes\scripts\v25\v645_convertible_bond_conversion_price_terms_source_pilot.py
- `stratum(symbol)` — 
- `universe()` — 
- `sampled_symbols()` — 
- `get_json(session, url, params)` — 
- `fetch_candidates(symbol)` — 
- `body_for(candidate)` — 
- `main()` — 

## hermes\scripts\v25\v647_cash_distribution_terms_same_identity_recovery.py
- `destination(row)` — 
- `valid(row)` — 
- `save(path, doc)` — 
- `fetch(row)` — 
- `main()` — 

## hermes\scripts\v25\v648_cash_distribution_terms_raw_full_coverage_identity_audit.py
- `event_map()` — 
- `raw_path(event)` — 
- `read_doc(path)` — 
- `audit(event)` — 
- `main()` — 

## hermes\scripts\v25\v650_explicit_cash_distribution_term_catalog.py
- `docs()` — 
- `candidate_matches(text)` — 
- `main()` — 

## hermes\scripts\v25\v651_explicit_cash_distribution_term_independent_oracle.py
- `rows()` — 
- `covered_by_anchor(text, position)` — 
- `oracle_accept(doc)` — 
- `primary_rows(path)` — 
- `main()` — 

## hermes\scripts\v25\v653_cash_distribution_event_daily_session_coverage_audit.py
- `cache_path(symbol)` — 
- `date_list(path)` — 
- `main()` — 

## hermes\scripts\v25\v654_two_sided_leverage_source_pit_audit.py
- `valid(ex, p)` — 
- `audit(ex)` — 
- `main()` — 

## hermes\scripts\v25\v655_two_sided_leverage_convergence_fvg_seed.py
- `pos(x)` — 
- `raw(ex, d)` — 
- `events()` — 
- `bars(sym)` — 
- `highs(xs)` — 
- `chain(e, xs, hs)` — 
- `main()` — 

## hermes\scripts\v25\v656_v654_independent_raw_oracle.py
- `n(x)` — 
- `rows(ex, d)` — 
- `rebuild_events()` — 
- `bars(sym)` — 
- `identity(sym, event, x)` — 
- `main()` — 

## hermes\scripts\v25\v657_v654_frozen_strict_t1_replay.py
- `n(x)` — 
- `bars(sym)` — 
- `pivots(x)` — 
- `target(x, signal, entry, stop)` — 
- `exit(x, e, entry, stop, tp)` — 
- `metrics(a)` — 
- `main()` — 

## hermes\scripts\v25\v65_closed_loop_90d_review.py
- `f(x, d)` — 
- `i(x, d)` — 
- `dkey(v)` — 
- `load_json(path, default)` — 
- `kpath(sym)` — 
- `kdate(kl, idx)` — 
- `pct(a, b)` — 
- `mean(vals)` — 
- `review_trade(t)` — 
- `bucket(rows, field)` — 
- `main()` — 

## hermes\scripts\v25\v65_engine.py
- `f(x, d)` — 
- `load(p, d)` — 
- `pass_v65(t)` — 
- `metrics(rows, weighted)` — 
- `main()` — 

## hermes\scripts\v25\v65_quality_metrics.py
- `f(x, d)` — 
- `main()` — 

## hermes\scripts\v25\v65_release_gate.py
- `load(p, d)` — 
- `main()` — 

## hermes\scripts\v25\v65_sample_bias_audit.py
- `main()` — 

## hermes\scripts\v25\v65_signal_sequence_audit.py
- `_i(x, default)` — 
- `_load(p, default)` — 
- `main()` — 

## hermes\scripts\v25\v65_t1_audit.py
- `d(x)` — 
- `main()` — 

## hermes\scripts\v25\v65_trade_provenance_audit.py
- `_i(x, default)` — 
- `_f(x, default)` — 
- `_load(path, default)` — 
- `_trade_file()` — 
- `_families_for_key(key, trade)` — 
- `_nearest_signal(signals, idx, families)` — 
- `_check_idx(trade, signals, key)` — 
- `audit_trade(trade, signals)` — 
- `main()` — 

## hermes\scripts\v25\v665_hkex_stock_connect_holdings_source_qualification.py
- `hidden_form_values(page)` — 
- `probe(requested_date)` — 
- `main()` — 

## hermes\scripts\v25\v669_institutional_survey_pit_source_qualification.py
- `request_page(page)` — 
- `atomic_write(path, text)` — 
- `day(value)` — 
- `event_key(row)` — 
- `participant_key(row)` — 
- `main()` — 

## hermes\scripts\v25\v66_closed_loop_90d_review.py
- `f(x, d)` — 
- `i(x, d)` — 
- `dkey(v)` — 
- `load_json(path, default)` — 
- `kpath(sym)` — 
- `kdate(kl, idx)` — 
- `pct(a, b)` — 
- `mean(vals)` — 
- `review_trade(t)` — 
- `bucket(rows, field)` — 
- `main()` — 

## hermes\scripts\v25\v66_daily_completeness_gate.py
- `load(path, default)` — 
- `dkey(v)` — 
- `symbol_from_file(fp)` — 
- `latest_date(fp)` — 
- `main()` — 

## hermes\scripts\v25\v66_engine.py
- `f(x, d)` — 
- `load(p, d)` — 
- `pass_v66(t)` — 
- `metrics(rows)` — 
- `main()` — 

## hermes\scripts\v25\v66_extra_hard_gates.py
- `load(path, default)` — 
- `run(script)` — 
- `main()` — 

## hermes\scripts\v25\v66_integrated_repair_closure.py
- `load(path, default)` — 
- `f(v)` — 
- `pct(n, d)` — 
- `q(vals)` — 
- `main()` — 

## hermes\scripts\v25\v66_live_execution_audit.py
- `load(path, default)` — 
- `date_key(v)` — 
- `f(v)` — 
- `zone_bounds(p)` — 
- `main()` — 

## hermes\scripts\v25\v66_live_vs_backtest_gap_audit.py
- `load(path, default)` — 
- `dkey(v)` — 
- `f(v)` — 
- `pct(n, d)` — 
- `q(vals)` — 
- `bdays(a, b)` — 
- `main()` — 

## hermes\scripts\v25\v66_multi_retrace_rank_audit.py
- `load(path, default)` — 
- `f(x, default)` — 
- `i(x, default)` — 
- `kpath(symbol)` — 
- `touched_zone(bar, low, high)` — 
- `date_of(klines, idx)` — 
- `rank_trade(t)` — 
- `bucket(rows, key_fn)` — 
- `main()` — 

## hermes\scripts\v25\v66_ob_loss_bucket_audit.py
- `load(path, default)` — 
- `f(x, default)` — 
- `i(x, default)` — 
- `kpath(symbol)` — 
- `pct(a, b)` — 
- `date_of(klines, idx)` — 
- `replay_trade(t)` — 
- `main()` — 

## hermes\scripts\v25\v66_phase2_repaired_backtest.py
- `d(b)` — 
- `f(v)` — 
- `simulate(klines, entry_idx, pick)` — 
- `make_pick(symbol, klines, z, c, entry_idx, baseline)` — 
- `replay_file(kf, baseline)` — 
- `metrics(trades)` — 
- `bucket(trades, field)` — 
- `bucket_fn(trades, fn)` — 
- `retr_bin(t)` — 
- `sl_bin(t)` — 
- `score_bin(t)` — 
- `top_combos(trades, min_n)` — 
- `production_profiles(trades)` — 
- `main()` — 

## hermes\scripts\v25\v66_pollution_quarantine.py
- `load(path, default)` — 
- `save(path, data)` — 
- `date_key(v)` — 
- `is_clean(row)` — 
- `is_diagnostic_closed_position(pos)` — 
- `is_diagnostic_review(review)` — 
- `main()` — 

## hermes\scripts\v25\v66_quality_metrics.py
- `f(x, d)` — 
- `main()` — 

## hermes\scripts\v25\v66_release_gate.py
- `load(p, d)` — 
- `main()` — 

## hermes\scripts\v25\v66_repair_monitor_state.py
- `backup(path)` — 
- `main()` — 

## hermes\scripts\v25\v66_sample_bias_audit.py
- `main()` — 

## hermes\scripts\v25\v66_signal_semantic_audit.py
- `load(path, default)` — 
- `f(x, default)` — 
- `i(x, default)` — 
- `kpath(symbol)` — 
- `swing_high(klines, idx, left, right)` — 
- `swing_low(klines, idx, left, right)` — 
- `latest_confirmed_swing_high_before(klines, idx)` — 
- `latest_confirmed_swing_low_before(klines, idx)` — 
- `nearest_opposite_candle_before(klines, event_idx, direction, max_back)` — 
- `audit_trade(t)` — 
- `main()` — 

## hermes\scripts\v25\v66_signal_sequence_audit.py
- `_i(x, default)` — 
- `_load(p, default)` — 
- `main()` — 

## hermes\scripts\v25\v66_t1_audit.py
- `d(x)` — 
- `main()` — 

## hermes\scripts\v25\v66_trade_provenance_audit.py
- `_i(x, default)` — 
- `_f(x, default)` — 
- `_load(path, default)` — 
- `_trade_file()` — 
- `_families_for_key(key, trade)` — 
- `_nearest_signal(signals, idx, families)` — 
- `_check_idx(trade, signals, key)` — 
- `audit_trade(trade, signals)` — 
- `main()` — 

## hermes\scripts\v25\v670_institutional_survey_source_recovery.py
- `atomic_json(path, payload)` — 
- `day(value)` — 
- `event_key(row)` — 
- `participant_key(row)` — 
- `request_page(year, page)` — 
- `connect()` — 
- `commit_page(db, result, expected)` — 
- `progress_payload(db, expected, failures)` — 
- `build_catalog(db, out_path)` — 
- `main()` — 
- `identity_key(row)` — 
- `flush()` — 

## hermes\scripts\v25\v671_institutional_survey_post_disclosure_absorption_seed_generator.py
- `d(x)` — 
- `n(x)` — 
- `bars(symbol)` — 
- `pivot_low(b, j)` — 
- `unmitigated_anchors(b, sweep)` — 
- `canonical_anchor(b, sweep)` — 
- `canonical_anchors_by_sweep(b)` — Exact one-pass equivalent of canonical_anchor(b, sweep) for every sweep.
- `pivot_high(b, j)` — 
- `session_index_by_date(b, date)` — 
- `main()` — 

## hermes\scripts\v25\v673_eastmoney_m15_source_qualification.py
- `request_rows(secid)` — 
- `day_slots(timestamps, day)` — 
- `probe(symbol, secid)` — 
- `passes(row)` — 
- `main()` — 

## hermes\scripts\v25\v677_aggregate_shards.py

## hermes\scripts\v25\v677_three_timeframe_semantic_source_audit.py
- `number(value)` — 
- `read_gz(path)` — 
- `daily_rows(path)` — 
- `m60_rows(path, daily_by_date)` — 
- `aggregate_daily_from_m60(bars)` — 
- `weekly_rows(daily)` — Aggregate only continuous same-segment daily bars; ISO weeks do not bridge a quarantine.
- `contiguous_segments(rows)` — 
- `primitives_a(rows, frame)` — Reference scan: pivot confirmation -> one-time close breaks -> wick/reclaim sweeps -> even
- `primitives_b(rows, frame)` — Independent formulation: build confirmed pivot maps first, then evaluate each completed ba
- `symbol_from_path(path)` — 
- `main()` — 

## hermes\scripts\v25\v677_weekly_daily_m60_pure_smc_source_audit.py
- `num(x)` — 
- `load_gz(p)` — 
- `date8(x)` — 
- `normalize_daily(raw)` — 
- `normalize_m60(raw)` — 
- `weekly(daily)` — 
- `pivots(rows)` — 
- `semantic_a(rows)` — 
- `semantic_b(rows)` — 
- `main()` — 

## hermes\scripts\v25\v678_outcome_blind_wdh_state_machine_seeds.py
- `by_type(events, name)` — 
- `index_by_time(rows)` — 
- `timekey(value)` — Canonical chronological key across D=YYYYMMDD and H=YYYY-MM-DD HH:MM:SS.
- `after(events, timestamp, segment, index, rows)` — 
- `timekey(value)` — Canonical order across daily YYYYMMDD and 60m ISO timestamps.
- `weekly_permissions(weekly, events)` — 
- `selected_w1(perms, daily_date)` — 
- `cancel(row, code)` — 
- `symbol_chains(symbol, daily, h60)` — 
- `main()` — 

## hermes\scripts\v25\v678_verify_artifact_contract.py
- `key(v)` — 

## hermes\scripts\v25\v679_independent_wdh_identity_oracle.py
- `by_type(events, name)` — 
- `index_by_time(rows)` — 
- `timekey(value)` — Canonical chronological key across D=YYYYMMDD and H=YYYY-MM-DD HH:MM:SS.
- `after(events, timestamp, segment, index, rows)` — 
- `weekly_permissions(weekly, events)` — 
- `selected_w1(perms, daily_date)` — 
- `cancel(row, code)` — 
- `symbol_chains(symbol, daily, h60)` — 
- `main()` — 

## hermes\scripts\v25\v67_directional_edge_gate.py
- `f(x, default)` — 
- `load_klines(symbol)` — 
- `forward_return(bars, entry_idx, horizon)` — 
- `summarize(vals)` — 
- `main()` — 

## hermes\scripts\v25\v67_promotion_gate.py
- `load(path, default)` — 
- `main()` — 

## hermes\scripts\v25\v67_signal_semantic_gate.py
- `load(path, default)` — 
- `kpath(symbol)` — 
- `i(x, default)` — 
- `audit_trade(t)` — 
- `main()` — 

## hermes\scripts\v25\v67_strict_engine.py
- `load_json(path, default)` — 
- `symbol_from_path(path)` — 
- `next_swing_target(klines, entry_idx, entry_price)` — 
- `strict_pinbar_or_reclaim(klines, idx, zone)` — 
- `build_setups(symbol, raw_klines)` — 
- `backtest(setups, klines)` — 
- `metrics(trades)` — 
- `main()` — 

## hermes\scripts\v25\v680_compare_v678_v679_identities.py
- `load_report(p)` — 
- `rows(path)` — 
- `key(x)` — 
- `digest(s)` — 
- `main()` — 

## hermes\scripts\v25\v681_frozen_t1_structure_replay.py
- `read_csv(path)` — 
- `identity(row)` — 
- `digest(items)` — 
- `ts_date(timestamp)` — 
- `idx(rows)` — 
- `target_at_entry(daily, weekly, entry_date, entry_price)` — Nearest higher confirmed weekly BSL, otherwise nearest daily swing high.
- `replay_row(seed, cache)` — 
- `metric(rows)` — 
- `main()` — 
- `candidates(events, kind)` — 

## hermes\scripts\v25\v681_single_frozen_t1_structure_replay.py
- `load_rows(symbol)` — 
- `tk(v)` — 
- `tdate(v)` — 
- `identity(r)` — 
- `f(v)` — 
- `find_bar(rows, t)` — 
- `confirmed_highs(rows, frame)` — 
- `target_at(entry_i, entry_price, daily, h60)` — 
- `replay_one(r, daily, h60)` — 
- `main()` — 

## hermes\scripts\v25\v681_single_frozen_wdh_strict_t1_replay.py
- `day(t)` — 
- `f(value)` — 
- `identity(row)` — 
- `digest(items)` — 
- `active_unconsumed_highs(rows, events, entry_time)` — Confirmed pivot highs visible before entry and not raided before entry.
- `structural_target(daily, entry_time, entry)` — 
- `replay(seed, daily, h60)` — 
- `closed(base, entry, sl, tp, risk_pct, planned_rr)` — 
- `metrics(rows)` — 
- `load_symbol(symbol)` — 
- `main()` — 

## hermes\scripts\v25\v682_closed_ontology_structural_integrity_postmortem.py
- `date(x)` — 
- `days(a, b)` — 
- `main()` — 

## hermes\scripts\v25\v682_independent_frozen_replay_metric_audit.py
- `ident(r)` — 
- `date(v)` — 
- `main()` — 

## hermes\scripts\v25\v682_v681_frozen_replay_postmortem.py
- `f(x)` — 
- `d(t)` — 
- `pct(a, b)` — 
- `met(rs)` — 
- `main()` — 

## hermes\scripts\v25\v683_wdh_lifecycle_cancellation_audit.py
- `day(x)` — 
- `main()` — 

## hermes\scripts\v25\v684_lifecycle_safe_wdh_state_machine_seeds.py
- `by_type(events, name)` — 
- `index_by_time(rows)` — 
- `timekey(value)` — Canonical chronological key across D=YYYYMMDD and H=YYYY-MM-DD HH:MM:SS.
- `after(events, timestamp, segment, index, rows)` — 
- `timekey(value)` — Canonical order across daily YYYYMMDD and 60m ISO timestamps.
- `weekly_permissions(weekly, events)` — 
- `selected_w1(perms, daily_date)` — 
- `cancel(row, code)` — 
- `lifecycle_cancel_code(daily, h60, weekly)` — Hard cancellations maintained to the next executable open, no outcomes.
- `symbol_chains(symbol, daily, h60)` — 
- `main()` — 

## hermes\scripts\v25\v684_persistent_validity_poi_contained_chains.py
- `timekey(value)` — 
- `index(rows)` — 
- `typed(events, kind)` — 
- `later(events, stamp, segment, rows, pos)` — 
- `intersects(bar, low, high)` — 
- `cancel(row, code)` — 
- `permissions(weekly, events)` — 
- `active_w1(perms, daily_time, segment)` — 
- `weekly_invalidated(weekly, w1, until_time)` — 
- `symbol_chains(symbol, daily, h60)` — 
- `main()` — 

## hermes\scripts\v25\v685_independent_lifecycle_safe_wdh_identity_oracle.py
- `by_type(events, name)` — 
- `index_by_time(rows)` — 
- `timekey(value)` — Canonical chronological key across D=YYYYMMDD and H=YYYY-MM-DD HH:MM:SS.
- `after(events, timestamp, segment, index, rows)` — 
- `timekey(value)` — Canonical order across daily YYYYMMDD and 60m ISO timestamps.
- `weekly_permissions(weekly, events)` — 
- `selected_w1(perms, daily_date)` — 
- `cancel(row, code)` — 
- `lifecycle_cancel_code(daily, h60, weekly)` — Hard cancellations maintained to the next executable open, no outcomes.
- `symbol_chains(symbol, daily, h60)` — 
- `main()` — 

## hermes\scripts\v25\v686_compare_v684_v685_identities.py
- `rows(path)` — 
- `key(x)` — 
- `digest(s)` — 
- `main()` — 

## hermes\scripts\v25\v687_unique_liquidity_lifecycle_safe_seeds.py
- `by_type(events, name)` — 
- `index_by_time(rows)` — 
- `timekey(value)` — Canonical chronological key across D=YYYYMMDD and H=YYYY-MM-DD HH:MM:SS.
- `after(events, timestamp, segment, index, rows)` — 
- `timekey(value)` — Canonical order across daily YYYYMMDD and 60m ISO timestamps.
- `weekly_permissions(weekly, events)` — 
- `selected_w1(perms, daily_date)` — 
- `cancel(row, code)` — 
- `lifecycle_cancel_code(daily, h60, weekly)` — Hard cancellations maintained to the next executable open, no outcomes.
- `canonical_ssl_events(events)` — One chain reference per sweep bar: most recently formed raided pool.
- `symbol_chains(symbol, daily, h60)` — 
- `main()` — 

## hermes\scripts\v25\v688_independent_unique_liquidity_identity_oracle.py
- `by_type(events, name)` — 
- `index_by_time(rows)` — 
- `timekey(value)` — Canonical chronological key across D=YYYYMMDD and H=YYYY-MM-DD HH:MM:SS.
- `after(events, timestamp, segment, index, rows)` — 
- `timekey(value)` — Canonical order across daily YYYYMMDD and 60m ISO timestamps.
- `weekly_permissions(weekly, events)` — 
- `selected_w1(perms, daily_date)` — 
- `cancel(row, code)` — 
- `lifecycle_cancel_code(daily, h60, weekly)` — Hard cancellations maintained to the next executable open, no outcomes.
- `canonical_ssl_events(events)` — One chain reference per sweep bar: most recently formed raided pool.
- `symbol_chains(symbol, daily, h60)` — 
- `main()` — 

## hermes\scripts\v25\v689_compare_v687_v688_identities.py
- `load(path)` — 
- `key(x)` — 
- `digest(s)` — 
- `main()` — 

## hermes\scripts\v25\v68_directional_edge_gate.py
- `f(x, default)` — 
- `load_klines(symbol)` — 
- `forward_return(bars, entry_idx, horizon)` — 
- `summarize(vals)` — 
- `main()` — 

## hermes\scripts\v25\v68_directional_engine.py
- `load_json(path, default)` — 
- `symbol_from_path(path)` — 
- `prior_swing_low(swings, idx)` — 
- `find_ssl_sweep(klines, swing_lows, start, end)` — 
- `has_fvg_context(fvgs, sweep_idx, confirm_idx)` — 
- `classify_direction(klines, reg, zone, ev)` — 
- `next_target(klines, entry_idx, entry_price, broken_swing)` — 
- `build_setups(symbol, raw_klines)` — 
- `backtest(setups, klines)` — 
- `metrics(trades)` — 
- `main()` — 

## hermes\scripts\v25\v68_limit_candidate.py
- `f(x)` — 
- `date_of(ks, idx)` — 
- `recent_swing_low_price(ks, upto, lookback)` — 
- `recent_bsl_price(ks, after_idx, before_idx, fallback_rr_tp)` — 
- `first_limit_fill(ks, start_idx, end_idx, limit_price)` — Validated limit fill: no assumed fill; bar must trade through limit.
- `simulate(ks, entry_idx, ep, sl, tp1)` — 
- `build_trades(symbol, ks)` — 
- `replay_file(kf)` — 
- `metrics(ts)` — 
- `bucket(ts, fn)` — 
- `audit(ts)` — 
- `make_picks(ts)` — 
- `main()` — 

## hermes\scripts\v25\v68_promotion_gate.py
- `load(path, default)` — 
- `main()` — 

## hermes\scripts\v25\v68_signal_semantic_gate.py
- `load(path, default)` — 
- `kpath(symbol)` — 
- `i(x, default)` — 
- `audit_trade(t)` — 
- `main()` — 

## hermes\scripts\v25\v68_sl_autopsy.py
- `f(x)` — 
- `load_ks(sym)` — 
- `dist(ts, fn)` — 

## hermes\scripts\v25\v690_v687_outcome_blind_support_gate.py
- `main()` — 

## hermes\scripts\v25\v692_wdh_research_frontier_reconciliation.py
- `main()` — 

## hermes\scripts\v25\v694_short_covering_smc_reversal_seed.py
- `pos(x)` — 
- `raw(ex, d)` — 
- `events()` — 
- `daily(s)` — 
- `pivots(r)` — 
- `chain(e, r, lo, hi)` — 
- `main()` — 

## hermes\scripts\v25\v696_research_completion_reconciliation.py
- `load(p)` — 
- `sha(p)` — 
- `main()` — 

## hermes\scripts\v25\v697_pure_smc_ssl_reclaim_seed.py
- `fnum(v)` — 
- `datekey(v)` — 
- `bars_for(path)` — 
- `is_confirmed_swing_low(bars, j)` — 
- `volume_rank_prior(values, current)` — 
- `canonical_swept_swing_low(bars, sweep_idx, swing_indices)` — Nearest confirmed, still-unmitigated SSL actually swept and reclaimed.
- `scan_symbol(symbol, bars)` — 
- `main()` — 

## hermes\scripts\v25\v698_pure_smc_ssl_reclaim_oracle.py
- `number(x)` — 
- `day(x)` — 
- `read_bars(p)` — 
- `low_pivot(b, j)` — 
- `canonical_anchor(b, sweep_idx, pivots)` — Independent implementation of the nearest prior confirmed unmitigated SSL.
- `oracle_for(symbol, b)` — 
- `main()` — 

## hermes\scripts\v25\v699_pure_smc_ssl_reclaim_replay.py
- `num(x)` — 
- `day(x)` — 
- `load_bars(symbol)` — 
- `high_pivot(b, j)` — 
- `visible_target(b, sweep_idx, response_idx, entry)` — 
- `pct(x, base)` — 
- `replay(row, b)` — 
- `stats(rows)` — 
- `monthly_trade_count_gate(rows)` — 
- `main()` — 

## hermes\scripts\v25\v69_90wr_search.py
- `f(x)` — 
- `date_of(ks, idx)` — 
- `recent_swing_low(ks, upto, lookback)` — 
- `first_fill(ks, start_idx, end_idx, price)` — 
- `simulate(ks, entry_idx, ep, sl, tp, max_hold)` — 
- `setup_base(symbol, ks)` — 
- `replay_file(kf)` — 
- `metrics(rows)` — 
- `audit(rows)` — 
- `materialize(base, cfg)` — 
- `main()` — 

## hermes\scripts\v25\v69_high_wr_probe.py
- `f(x)` — 
- `d(ks, i)` — 
- `swing_low(ks, upto, lookback)` — 
- `first_fill(ks, start, end, price)` — 
- `sim(ks, entry_idx, ep, sl, tp, max_hold)` — 
- `add_metric(m, pnl, reason)` — 

## hermes\scripts\v25\v69_matrix_audit.py
- `f(x)` — 
- `date_of(ks, idx)` — 
- `pct(a, b)` — 
- `recent_swing_low(ks, upto, lookback)` — 
- `nearest_bsl_above(ks, from_idx, upto_idx, entry_price)` — 
- `first_limit_fill(ks, start_idx, end_idx, limit_price, zone_low)` — 
- `reclaim_entry(ks, poi, dbar, max_wait)` — 
- `executable_entry(ks, setup, entry_model)` — 
- `sl_price(ks, setup, entry_idx, entry_price, sl_model)` — 
- `tp_price(ks, setup, entry_idx, entry_price, sl, tp_model)` — 
- `simulate(ks, entry_idx, ep, sl, tp1)` — 
- `unique_setups(symbol, ks)` — 
- `variant_rows(symbol, ks)` — 
- `replay_file(kf)` — 
- `metrics(ts)` — 
- `bucket_key(t, name)` — 
- `bucket(ts, name)` — 
- `combo_table(ts)` — 
- `audit(ts)` — 
- `observation_report(obs_rows)` — 
- `main()` — 

## hermes\scripts\v25\v69_missing_gates_audit.py
- `f(value, default)` — 
- `pct(n, d)` — 
- `metrics(rows)` — 
- `add_features(row)` — 
- `bucket(rows, field)` — 
- `test_filter(rows, name, fn)` — 
- `combo_tests(rows, filters)` — 
- `same_symbol_random_edge_note(rows)` — 
- `main()` — 

## hermes\scripts\v25\v69_missing_gates_directional_edge.py
- `f(x, default)` — 
- `load_klines(symbol)` — 
- `forward_return(bars, entry_idx, horizon)` — 
- `summarize(vals)` — 
- `add_features(row)` — 
- `subset_predicates()` — 
- `edge_for_subset(name, rows)` — 
- `main()` — 

## hermes\scripts\v25\v69_unique_ld_matrix.py
- `f(x, default)` — 
- `d(b)` — 
- `atr(ks, idx, n)` — 
- `is_swing_low(ks, i, left, right)` — 
- `is_swing_high(ks, i, left, right)` — 
- `swings_until(ks, upto, left, right)` — 
- `find_ssl_sweeps(ks)` — 
- `find_displacement_after(ks, lbar, max_wait)` — 
- `demand_pois(ks, lbar, dbar)` — 
- `first_touch_idx(ks, poi, dbar, max_wait)` — 
- `find_reclaim_idx(ks, poi, dbar, max_wait)` — 
- `nearest_bsl_target(ks, upto, entry)` — 
- `recent_swing_low(ks, upto, fallback)` — 
- `unique_setup_key(L, D, poi)` — 
- `setup_quality_key(setup)` — 
- `build_unique_setups(symbol, ks)` — 
- `entry_variant(ks, setup, kind)` — 
- `sl_variant(ks, setup, entry_idx, entry_price, kind)` — 
- `tp_variant(setup, entry, sl, kind)` — 
- `simulate(ks, entry_idx, ep, sl, tp1)` — 
- `retrace_pct(ks, setup, entry_idx)` — 
- `run_matrix_for_setup(ks, setup)` — 
- `replay_file(kf)` — 
- `metrics(rows)` — 
- `bucket_name(field, row)` — 
- `bucket(rows, field)` — 
- `combo_ranking(rows, candidate_only)` — 
- `audit(rows)` — 
- `write_md(report)` — 
- `main()` — 

## hermes\scripts\v25\v700_pure_smc_ssl_reclaim_current_scanner.py
- `n(x)` — 
- `d(x)` — 
- `bars(p)` — 
- `pivot_low(b, j)` — 
- `unmitigated_anchors(b, sweep)` — 
- `canonical_anchor(b, sweep)` — Nearest prior confirmed, unmitigated SSL swept and reclaimed by `sweep`.
- `pivot_high(b, j)` — 
- `target(b, sweep, minimum)` — 
- `candidate(sym, b, market_date)` — 
- `diagnostic_progress(sym, b, market_date)` — Outcome-blind current-date funnel for observability only.
- `main()` — 

## hermes\scripts\v25\v701_pure_smc_post_close_observer.py
- `run(cmd, timeout)` — 
- `load(path)` — 
- `main()` — 

## hermes\scripts\v25\v70_build_precision_candidate.py
- `metrics(rs)` — 
- `audit(rs)` — 

## hermes\scripts\v25\v70_combo_search.py
- `f(x, default)` — 
- `enrich(row)` — 
- `metrics(rows)` — 
- `make_predicates()` — 
- `combo_key_score(metric)` — 
- `main()` — 

## hermes\scripts\v25\v70_exante_filter_search.py
- `m(rs)` — 

## hermes\scripts\v25\v70_fast_repair_from_v68.py
- `f(x, default)` — 
- `similar(a, b)` — 
- `add_features(r)` — 
- `quality_key(t)` — 
- `dedup(rows)` — 
- `metrics(rows)` — 
- `bucket(rows, fn)` — 
- `audit(rows)` — 
- `gates()` — 
- `search(rows)` — 
- `apply_cfg(rows, cfg)` — 
- `add(name, fn, cfg)` — 

## hermes\scripts\v25\v70_fast_signal_gate_search.py
- `f(x, d)` — 
- `date(b)` — 
- `pct(a, b)` — 
- `ma(vals, n, i)` — 
- `metrics_idx(rows, idxs)` — 

## hermes\scripts\v25\v70_high_confidence_repair.py
- `f(x, default)` — 
- `date_of(ks, idx)` — 
- `load_ks(kf)` — 
- `market_features(ks, idx)` — 
- `make_trade(symbol, ks, setup)` — 
- `similar(a, b)` — 
- `quality_key(t)` — 
- `dedup_similar(rows)` — 
- `metrics(rows)` — 
- `bucket(rows, fn)` — 
- `filter_search(rows)` — Beam-search pre-entry gates instead of cartesian brute force.
- `audit(rows)` — 
- `apply_cfg(rows, cfg)` — 
- `main()` — 
- `add(name, fn, cfg)` — 
- `score(sel)` — 

## hermes\scripts\v25\v70_precision_candidate.py
- `f(x, d)` — 
- `date(b)` — 
- `ma(vals, n, i)` — 
- `pct(a, b)` — 
- `metrics(rows)` — 
- `enrich(t)` — 
- `gate(r)` — 

## hermes\scripts\v25\v70_reaction_confirm_candidate.py
- `f(x, default)` — 
- `d(b)` — 
- `atr(ks, idx, n)` — 
- `ma(vals, n)` — 
- `is_sw_low(ks, i, L, R)` — 
- `is_sw_high(ks, i, L, R)` — 
- `swings_until(ks, upto)` — 
- `trend(ks, idx)` — 
- `find_ssl(ks)` — 
- `displacement(ks, lbar, max_wait)` — 
- `fvg_pois(ks, lbar, dbar)` — 
- `recent_swing_low(ks, idx, fallback)` — 
- `confirm_after_touch(ks, poi, dbar, mode)` — 
- `simulate(ks, eidx, ep, sl, tp, max_hold)` — 
- `rows_for(symbol, ks)` — 
- `replay(kf)` — 
- `metrics(rs)` — 
- `bucket(rs, fn)` — 
- `audit(rs)` — 
- `main()` — 

## hermes\scripts\v25\v70_signal_gate_search.py
- `f(x, d)` — 
- `date(b)` — 
- `ma(vals, n, i)` — 
- `pct(a, b)` — 
- `metrics(rows)` — 
- `gate_defs()` — 

## hermes\scripts\v25\v70_sl_root_cause_audit.py
- `f(x, default)` — 
- `ma(vals, n)` — 
- `load_ks(symbol)` — 
- `date_idx(ks, date)` — 
- `atr(ks, idx, n)` — 
- `swing_low(ks, i, left, right)` — 
- `swing_high(ks, i, left, right)` — 
- `recent_structure(ks, idx, lookback)` — 
- `trend_context(ks, idx)` — 
- `classify_trade(t)` — 
- `root_priority(tags, exit_reason)` — 
- `metrics(rows)` — 
- `bucket(rows, field)` — 
- `main()` — 

## hermes\scripts\v25\v70_smart_money_position_audit.py
- `f(x, default)` — 
- `d(b)` — 
- `load_ks(symbol)` — 
- `atr(ks, idx, n)` — 
- `is_swing_low(ks, i, L, R)` — 
- `is_swing_high(ks, i, L, R)` — 
- `recent_swings(ks, idx, lookback)` — 
- `find_last_down_candle(ks, lbar, dbar)` — 
- `overlap_ratio(a_low, a_high, b_low, b_high)` — 
- `impulse_position(ks, t)` — 
- `reaction_before_entry(ks, t)` — 
- `trend_context(ks, idx)` — 
- `audit_trade(t)` — 
- `metrics(rows)` — 
- `bucket(rows, fn)` — 
- `main()` — 

## hermes\scripts\v25\v71_anti_live_sl_gate.py
- `f(x, d)` — 
- `load(path, default)` — 
- `kline_path(symbol)` — 
- `dkey(v)` — 
- `load_bars(symbol)` — 
- `bar_by_date(symbol, date)` — 
- `metrics(rows)` — 
- `gate(t)` — 
- `main()` — 

## hermes\scripts\v25\v71_context_event_poi_state_machine.py
- `f(x, default)` — 
- `_bar(b, k)` — 
- `classify_market_context(ks, idx, lookback)` — 
- `detect_smc_events(ks, idx, lookback)` — 
- `_last_bearish_before(ks, idx, max_back)` — 
- `build_demand_pois(ks, events, idx)` — 
- `evaluate_entry_window(ks, poi, start_idx, entry_idx)` — 
- `classify_setup_story(ks, ctx, events, pois, entry_idx)` — 

## hermes\scripts\v25\v71_context_poi_gate_search.py
- `metrics(rs)` — 
- `main()` — 

## hermes\scripts\v25\v71_context_poi_state_audit.py
- `f(x, default)` — 
- `ds(b)` — 
- `load_ks(symbol)` — 
- `atr(ks, idx, n)` — 
- `swing_high(ks, i, L, R)` — 
- `swing_low(ks, i, L, R)` — 
- `swings_before(ks, idx, lookback, L, R)` — 
- `market_context(ks, idx)` — 
- `detect_ssl_sweep(ks, liq_idx)` — 
- `structure_event_between(ks, start, end)` — 
- `poi_position_and_health(ks, t)` — 
- `classify_story(ctx, sweep, struct, poi)` — 
- `metrics(rows)` — 
- `bucket(rows, key)` — 
- `audit_trade(t)` — 
- `main()` — 

## hermes\scripts\v25\v71_smart_money_position_engine.py
- `f(x, default)` — 
- `date_of(ks, idx)` — 
- `recent_swing_low(ks, upto, lookback)` — 
- `recent_bsl(ks, after_idx, before_idx, min_target)` — 
- `overlap_zone(a, b)` — 
- `smart_money_pois(ks, lbar, dbar)` — Return only OB / OB-FVG overlap zones. FVG solo is evidence, not entry.
- `impulse_pd_zone(ks, L, D, price)` — 
- `find_reaction_then_entry(ks, poi, dbar, max_wait)` — 
- `simulate(ks, entry_idx, ep, sl, tp1)` — 
- `build_trades(symbol, ks)` — 
- `replay_file(kf)` — 
- `metrics(ts)` — 
- `bucket(ts, fn)` — 
- `audit(ts)` — 
- `build_picks(ts, limit)` — 
- `main()` — 

## hermes\scripts\v25\v72_audit.py
- `f(x)` — 
- `met(rs)` — 
- `group(keyfn, source)` — 

## hermes\scripts\v25\v72_layered_sl_buffer.py
- `f(value, default)` — 
- `load_json(path)` — 
- `pass_v66_reentry_overlay(trade)` — 
- `enrich(trade)` — 
- `tier_for(row)` — 
- `metrics(rows)` — 
- `pick_from_trade(row)` — 
- `main()` — 

## hermes\scripts\v25\v72_sweep_origin_ob_engine.py
- `f(x, default)` — 
- `date_of(ks, idx)` — 
- `recent_swing_low(ks, upto, lookback)` — 
- `recent_bsl(ks, after_idx, before_idx, min_target)` — 
- `overlap_zone(a, b)` — 
- `smart_money_pois(ks, lbar, dbar)` — Return sweep-origin smart-money zones.
- `impulse_pd_zone(ks, L, D, price)` — 
- `find_reaction_then_entry(ks, poi, dbar, max_wait)` — 
- `simulate(ks, entry_idx, ep, sl, tp1)` — 
- `build_trades(symbol, ks)` — 
- `replay_file(kf)` — 
- `metrics(ts)` — 
- `bucket(ts, fn)` — 
- `audit(ts)` — 
- `build_picks(ts, limit)` — 
- `main()` — 

## hermes\scripts\v25\v73_structural_environment_gate_search.py
- `f(x, default)` — 
- `d(b)` — 
- `load_ks(kf)` — 
- `symbol_from_file(kf)` — 
- `confirmed_swing_series(ks)` — Non-leaking daily structural state using only swings already confirmed by idx.
- `build_environment(files)` — 
- `metrics(ts)` — 
- `bucket(ts, key)` — 
- `annotate_trades(trades, env, stock_state)` — 
- `passes_gate(t, gate)` — 
- `main()` — 

## hermes\scripts\v25\v74_environment_state_machine.py
- `f(x, default)` — 
- `classify_market_env(row)` — Classify broad SMC environment into demand-valid/risk states.
- `is_valid_demand_zone(trade)` — 
- `classify_setup_story(trade)` — 
- `passes_v74_core_gate(trade)` — 
- `metrics(ts)` — 
- `bucket(rows, key)` — 
- `add_env_slopes(env_by_date)` — 
- `annotate_trades(trades, env)` — 
- `main()` — 

## hermes\scripts\v25\v75_post_entry_invalidation_audit.py
- `f(x, default)` — 
- `dt(bar)` — 
- `sym_to_cache(symbol)` — 
- `load_klines(symbol)` — 
- `metrics(rows, pnl_key)` — 
- `bucket(rows, key, pnl_key)` — 
- `confirmed_swings(ks, upto, left, right)` — 
- `prior_structure_anchors(ks, entry_idx, entry_price)` — 
- `first_event_after_entry(ks, trade, env_by_date, anchors)` — 
- `classify_primary_post_entry_fail(row)` — 
- `apply_early_exit(row, rule)` — 
- `main()` — 

## hermes\scripts\v25\v76_env_persistence_story_machine.py
- `f(x, default)` — 
- `date_key(t)` — 
- `metrics(rows)` — 
- `bucket(rows, key)` — 
- `env_window(env, dates, dt, n)` — 
- `annotate(rows, env)` — 
- `gate_search(rows)` — 
- `main()` — 

## hermes\scripts\v25\v76_environment_hysteresis_engine.py
- `f(x, default)` — 
- `dt(bar)` — 
- `load_json(path)` — 
- `symbol_cache_path(symbol)` — 
- `load_klines(symbol)` — 
- `prior_env_states(entry_date, env_by_date, window)` — 
- `annotate_environment_hysteresis(trade, env_by_date)` — 
- `v76_reject_reason(trade)` — 
- `passes_v76_entry_gate(trade)` — 
- `simulate_v76_exit(trade, klines, env_by_date)` — 
- `metrics(rows, pnl_key, exit_reason_key, hold_key)` — 
- `bucket(rows, key, pnl_key, exit_reason_key, hold_key)` — 
- `run_v76()` — 
- `write_markdown_report(report)` — 
- `main()` — 
- `row(label, m)` — 

## hermes\scripts\v25\v77_recovery_quality_gate_search.py
- `f(x, d)` — 
- `y(r)` — 
- `m(rows)` — 
- `bucket(rows, key)` — 
- `prior(rows, n)` — 
- `pass_candidate(r, cfg)` — 
- `main()` — 

## hermes\scripts\v25\v77_recovery_quality_state_machine.py
- `f(x, default)` — 
- `load_json(path)` — 
- `date_key(r)` — 
- `trade_key(r)` — 
- `load_klines(symbol)` — 
- `metrics(rows)` — 
- `bucket(rows, key)` — 
- `attach_v76_env_fields(rows)` — 
- `enrich_stock_pre_entry_features(rows)` — 
- `classify_recovery_quality(r)` — 
- `passes_v77_gate(r)` — 
- `reject_reason(r)` — 
- `gate_search(rows)` — 
- `main()` — 

## hermes\scripts\v25\v78_full_candidate_lifecycle_audit.py
- `sym_to_cache(symbol)` — 
- `load_klines(symbol)` — 
- `date_of(bar)` — 
- `find_idx_by_date(ks, date)` — 
- `metrics(rows)` — 
- `bucket(rows, key)` — 
- `prior_env_window(env, entry_date, n)` — 
- `annotate_trade(trade, env)` — 
- `main()` — 

## hermes\scripts\v25\v78_hysteresis_recovery_trend_gate.py
- `f(x, default)` — 
- `load_json(path)` — 
- `dt(b)` — 
- `load_klines(symbol)` — 
- `passes_v78_gate(r)` — 
- `reject_reason(r)` — 
- `simulate_env_exit(trade, klines, env_by_date)` — 
- `metrics(rows, prefix)` — 
- `bucket(rows, key, prefix)` — 
- `main()` — 

## hermes\scripts\v25\v78_smc_lifecycle_state_machine.py
- `f(x, default)` — 
- `_v(b, k)` — 
- `_date(b)` — 
- `classify_trend_regime(ks, idx, lookback)` — 
- `_last_bearish_before(ks, idx, max_back)` — 
- `_previous_low(ks, idx, lookback)` — 
- `_previous_high(ks, idx, lookback)` — 
- `detect_smc_lifecycle_event(ks, idx, trend, lookback)` — 
- `locate_demand_poi(ks, event)` — 
- `evaluate_entry_location(ks, poi, start_idx, entry_idx)` — 
- `classify_exit_semantics(ks, poi, entry_idx, max_idx)` — 

## hermes\scripts\v25\v79_full_candidate_v78_replay.py
- `f(x, default)` — 
- `load_json(path)` — 
- `dt(b)` — 
- `trade_year(r)` — 
- `date_key(r)` — 
- `load_klines(symbol)` — 
- `add_env_window_fields(rows, env_by_date)` — 
- `enrich_stock_pre_entry_features(rows)` — 
- `classify_recovery_quality(r)` — 
- `passes_v78_gate(r)` — 
- `reject_reason(r)` — 
- `simulate_env_exit(trade, klines, env_by_date)` — 
- `metrics(rows, prefix)` — 
- `bucket(rows, key, prefix)` — 
- `production_readiness(simulated)` — 
- `main()` — 

## hermes\scripts\v25\v79_full_lifecycle_audit.py
- `load_json(path)` — 
- `symbol_to_kline_path(symbol)` — 
- `get_date(row)` — 
- `metrics(rows)` — 
- `bucket(rows, key)` — 
- `annotate_env_and_v74(rows, env_by_date)` — 
- `lifecycle_for_trade(trade, ks)` — 
- `main()` — 

## hermes\scripts\v25\v79_lifecycle_gate_full_candidate.py
- `v(x)` — 
- `passes_v79_gate(r)` — 
- `reject_reason(r)` — 
- `resimulate_selected(r)` — 
- `metrics_v79(rows)` — 
- `bucket_v79(rows, key)` — 
- `main()` — 

## hermes\scripts\v25\v80_full_candidate_production_gate.py
- `f(x, default)` — 
- `load_json(path)` — 
- `trade_year(r)` — 
- `passes_v80_gate(r)` — 
- `reject_reason(r)` — 
- `metrics(rows, prefix)` — 
- `bucket(rows, key, prefix)` — 
- `production_readiness(simulated)` — 
- `main()` — 

## hermes\scripts\v25\v81_contextual_smc_generator.py
- `f(x, default)` — 
- `_v(b, key)` — 
- `_date(b)` — 
- `_env_state(env)` — 
- `_previous_high(ks, idx, lookback)` — 
- `_previous_low(ks, idx, lookback)` — 
- `_last_bearish_before(ks, idx, max_back)` — 
- `classify_context(ks, idx, env, lookback)` — Classify environment permission and local stock trend at idx.
- `detect_event(ks, idx, context, lookback)` — 
- `_future_liquidity_target(ks, event_idx, min_price, lookahead)` — 
- `locate_poi(ks, event, env)` — Find demand OB POI and validate it is below equilibrium/discount.
- `locate_entry(ks, poi, event_idx, max_wait)` — 
- `next_exit_semantic(ks, poi, start_idx)` — 
- `generate_candidates(symbol, ks, env_by_date, lookback)` — 

## hermes\scripts\v25\v81_full_market_scan.py
- `load_json(path)` — 
- `symbol_from_path(path)` — 
- `normalize_env(row)` — 
- `simulate_trade(c, ks)` — 
- `metrics(rows)` — 
- `bucket(rows, key)` — 
- `main()` — 

## hermes\scripts\v25\v82_apply_quality_gate.py
- `metrics(rows)` — 
- `bucket(rows, key)` — 
- `main()` — 

## hermes\scripts\v25\v82_gate_search.py
- `f(x, d)` — 
- `mask_for(fn)` — 
- `bit_indices(mask)` — 
- `metrics(idxs)` — 
- `eval_mask(mask)` — 
- `clean(d)` — 
- `obj(r)` — 

## hermes\scripts\v25\v82_gate_search_np.py
- `f(x, d)` — 
- `add(name, fam, fn)` — 
- `met(mask)` — 
- `rec(mask, names)` — 
- `clean(d)` — 
- `obj(r)` — 

## hermes\scripts\v25\v82_smart_money_quality_gate.py
- `f(x, default)` — 
- `enrich_v82_features(row)` — 
- `passes_v82_quality_gate(row)` — 

## hermes\scripts\v25\v83_apply_post_reclaim_takeover.py
- `load_json(path)` — 
- `kline_path(symbol)` — 
- `metrics(rows)` — 
- `bucket(rows, key)` — 
- `main()` — 

## hermes\scripts\v25\v83_post_reclaim_takeover_gate.py
- `f(x, default)` — 
- `_v(b, key)` — 
- `_date(b)` — 
- `evaluate_post_reclaim_takeover(row, ks, max_confirm_bars)` — Validate that smart money takes control after POI reclaim.
- `apply_v83_entry(row, ks, features)` — 

## hermes\scripts\v25\v84_apply_smart_money_path_split.py
- `load_json(path)` — 
- `normalize_env(row)` — 
- `kline_path(symbol)` — 
- `bar_date(b)` — 
- `enrich_path_features(row, ks)` — 
- `metrics(rows)` — 
- `bucket(rows, key)` — 
- `main()` — 

## hermes\scripts\v25\v84_smart_money_path_split_gate.py
- `f(x, default)` — 
- `_date_key(value)` — 
- `_env_state(row)` — 
- `_post_takeover_state(row, env_by_date)` — Return the broad environment at entry/takeover time.
- `_sweep_pierce_pct(row)` — 
- `evaluate_v84_path_gate(row, env_by_date)` — Split V83 into explicit smart-money paths.

## hermes\scripts\v25\v85_apply_production_gate.py
- `load_json(path)` — 
- `zone_width(row)` — 
- `passes_v85_production_gate(row)` — 
- `field_audit(rows)` — 
- `main()` — 

## hermes\scripts\v25\v85_full_market_scan.py
- `field_audit(rows)` — 
- `main()` — 

## hermes\scripts\v25\v85_gate_search.py
- `calc(mask)` — 
- `add(name, mask, group)` — 

## hermes\scripts\v25\v85_mixed_accumulation_generator.py
- `_v(b, key)` — 
- `zone_width_pct(row)` — 
- `classify_mixed_after_poi(ks, poi_or_row, market_state)` — 
- `_previous_high(ks, idx, lookback)` — 
- `_local_uptrend(ks, idx, lookback)` — 
- `_expanded_bos_event(ks, idx, lookback)` — 
- `_env_state(env)` — 
- `_normalize_contract(row, ks)` — 
- `_candidate_from_event(symbol, ks, env, event, max_wait)` — 
- `generate_v85_candidates(symbol, ks, env_by_date, lookbacks, max_wait)` — 

## hermes\scripts\v25\v86_loss_autopsy.py
- `kline_path(symbol)` — 
- `pct(a, b)` — 
- `safe_date(b)` — 
- `bucket(rows, key)` — 
- `enrich_trade(t, ks)` — 
- `quantile(vals, q)` — 
- `numeric_split(rows, field, cuts)` — 
- `per_trade_diagnosis(r)` — 
- `main()` — 

## hermes\scripts\v25\v86_production_gate.py
- `passes_v86_production_gate(row)` — 
- `production_criteria(rows)` — 
- `main()` — 

## hermes\scripts\v25\v87_mtf_entry_rr_matrix.py
- `f(x, default)` — 
- `d(b)` — 
- `tstamp(b)` — 
- `symkey(sym)` — 
- `load_json(p)` — 
- `kpath(sym, tf)` — 
- `ma(vals, n)` — 
- `daily_state(bars)` — 
- `slice_until(bars, date)` — 
- `slice_after(bars, date, max_days)` — 
- `find_m60_window_for_date(bars, entry_date, lookahead_days)` — 
- `compute_rr(entry, sl, tp)` — 
- `m60_state(bars)` — 
- `_swing_low(bars)` — 
- `m60_entry_plan(win, zone_low, zone_high, daily_entry, mode, sl_mode)` — 
- `tp_plan(entry, sl, liq, mode)` — 
- `simulate_exit_legs(daily, entry_price, sl, tp1, tp2, tp3)` — 
- `metrics(rows)` — 
- `bucket(rows, key)` — 
- `main()` — 

## hermes\scripts\v25\v88_apply_production_contract.py
- `f(x, default)` — 
- `load(path, default)` — 
- `date_key(v)` — 
- `kline_path(symbol)` — 
- `bar_date(b)` — 
- `slice_after(bars, date, max_days)` — 
- `tp_plan(entry, sl, liq)` — 
- `simulate_exit_legs(daily, entry_price, sl, tp1, tp2, tp3)` — 
- `metrics(rows)` — 
- `bucket(rows, key)` — 
- `apply_contract(base, v87, daily_bars)` — 
- `main()` — 

## hermes\scripts\v25\v89_recovery_known_target_repair.py
- `num(x, default)` — 
- `load(path, default)` — 
- `date_key(v)` — 
- `metrics(rows)` — 
- `bucket(rows, key)` — 
- `apply_contract(base, v87, candidate, gate_type)` — 
- `build_candidate(candidate, gate_type, keep, base_trades, base_picks, chosen)` — 
- `main()` — 

## hermes\scripts\v25\v90_3y_v86_gate_known_bsl_audit.py
- `num(x, default)` — 
- `date_key(x)` — 
- `symbol_path(symbol)` — 
- `load_ks(symbol, cache)` — 
- `payoff(rows)` — 
- `bucket(rows, key)` — 
- `annotate_gate_rows(rows)` — 
- `combos(rows)` — 
- `main()` — 

## hermes\scripts\v25\v90_daily_full_market_scanner.py
- `num(x, default)` — 
- `date_key(v)` — 
- `bar_date(b)` — 
- `v(b, key)` — 
- `atr(ks, idx, n)` — 
- `infer_family(row)` — 
- `fvg_source_label(row)` — 
- `v116_gate_reason(row)` — 
- `source_quality_fields(c, ks)` — 
- `v127_reclaim_geometry_fields(poi, entry, ks)` — 
- `v127_true_fvg_shadow_fields(c, ks)` — Attach true FVG_Demand shadow metadata without changing scanner identity.
- `v125_fvg_contract(row)` — 
- `v128_row_from_poi(c, poi, entry, ks, source)` — 
- `v128_parallel_shadow_candidates(c, ks)` — Emit standalone shadow candidates per POI source; never changes production rows.
- `dedupe_v128(rows)` — 
- `known_bsl_target(ks, entry_idx, entry_price, lookback)` — Find a pre-entry buy-side liquidity target: nearest prior swing/high above entry.
- `passes_v86_gate(row)` — 
- `recovery_substate(row, ks)` — 
- `v88_contract_from_candidate(c, ks)` — 
- `field_audit(rows)` — 
- `v127_shadow_audit(rows)` — 
- `bucket(rows, key)` — 
- `main()` — 
- `missing(rs)` — 
- `window(n)` — 

## hermes\scripts\v25\v91_mtf_entry_position_audit.py
- `F(x, d)` — 
- `D(x)` — 
- `bd(b)` — 
- `load(p)` — 
- `sp(sym)` — 
- `kpath(sym, tf)` — 
- `idx_by_date(ks, date)` — 
- `ma(a, n)` — 
- `state(bars)` — 
- `known_bsl(ks, ei, ep, look)` — 
- `v86_gate(r)` — 
- `gate_reason(r)` — 
- `entry_plans(r, ks, m60)` — 
- `sim(ks, start, ep, zl, zh, mode)` — 
- `met(rows)` — 
- `bucket(rows, key, minn)` — 
- `main()` — 

## hermes\scripts\v25\v91_shadow_zone_entry_scanner.py
- `num(x, default)` — 
- `date_key(v)` — 
- `bar_date(b)` — 
- `price_in_bar(b, price)` — 
- `v91_gate_reason(row)` — 
- `entry_plan_for(row)` — 
- `fill_idx_for_limit(row, ks, limit_price)` — 
- `contract_from_candidate(c, ks)` — 
- `field_audit(rows)` — 
- `bucket(rows, key)` — 
- `main()` — 

## hermes\scripts\v25\v91_smc_full_flow_solution_audit.py
- `load(path, default)` — 
- `num(x, default)` — 
- `date_key(x)` — 
- `win(row)` — 
- `metrics(rows)` — 
- `bucket(rows, key)` — 
- `production_filter(row)` — 
- `v87_combo(row)` — 
- `elite_filter(row)` — 
- `no_bear_any_tf(row)` — 
- `evaluate_v87_candidates(rows)` — 
- `field_audit(rows, keys)` — 
- `kline_path(symbol)` — 
- `enrich_production_rows(rows)` — Attach V88 scanner execution contract to historical V90 audit rows.
- `main()` — 

## hermes\scripts\v25\v92_recovery_time_stop_zone_mid_autopsy.py
- `load(path)` — 
- `num(x, default)` — 
- `metric(rows)` — 
- `bucket(rows, key, min_n)` — 
- `top_examples(rows, n)` — 
- `main()` — 

## hermes\scripts\v25\v93_recovery_time_runner_audit.py
- `num(x, default)` — 
- `load_rows()` — 
- `metric(rows)` — 
- `bucket(rows, key, min_n)` — 
- `zone_mid_micro(rows)` — 
- `recovery_gate_label(r)` — 
- `recovery_passes_v93(r)` — 
- `runner_variant_pnl(row, variant)` — 
- `apply_runner(rows, variant)` — 
- `years(rows)` — 
- `main()` — 

## hermes\scripts\v25\v94_post_exit_tp_sl_autopsy.py
- `num(x, default)` — 
- `kline_path(symbol)` — 
- `load_kline(symbol)` — 
- `index_by_date(ks)` — 
- `trade_exit_idx(tr, ks)` — 
- `close_at_entry(tr, ks)` — 
- `calc_post_exit(tr)` — 
- `pct(part, total)` — 
- `summary(rows)` — 
- `bucket(rows, key)` — 
- `main()` — 
- `avg(k)` — 
- `med(k)` — 

## hermes\scripts\v25\v95_exit_contract_autopsy.py
- `num(x, default)` — 
- `d(b)` — 
- `date_key(v)` — 
- `symkey(sym)` — 
- `kpath(sym)` — 
- `load_json(path, default)` — 
- `bars_after(bars, date, n)` — 
- `bars_from_entry_t1(bars, entry_date, n)` — 
- `risk_price(row)` — 
- `risk_pct(row)` — 
- `post_exit_profile(row, bars)` — 
- `classify_sl(row, prof)` — 
- `simulate_v95(row, daily)` — 
- `metrics(rows, pnl_key, reason_key)` — 
- `bucket(rows, key, pnl_key, reason_key)` — 
- `summarize_post(rows, reason)` — 
- `main()` — 

## hermes\scripts\v25\v96_adaptive_entry_exit_search.py
- `num(x, default)` — 
- `date_key(v)` — 
- `bd(b)` — 
- `symkey(sym)` — 
- `load_json(p, default)` — 
- `kpath(sym)` — 
- `clean_bars(rows)` — 
- `after_date(bars, date, n)` — 
- `entry_level(row, rule)` — 
- `wait_days_for_entry(rule)` — 
- `find_limit_entry(row, bars, rule)` — 
- `sl_price(row, entry, rule)` — 
- `tp_levels(row, entry, sl, rule)` — 
- `simulate_exit(row, bars, entry_date, entry, sl, exit_rule)` — 
- `post_after_exit(bars, exit_date, exit_price)` — 
- `metrics(rows, pnl, reason)` — 
- `baseline_metrics(rows)` — 
- `bucket(rows, key)` — 
- `baseline_post_exit(trades, kcache)` — 
- `run_search(write_outputs)` — 

## hermes\scripts\v25\v96_runner_sl_split_autopsy.py
- `num(x, default)` — 
- `date_key(v)` — 
- `runner_class(r)` — 
- `sl_class_v96(r)` — 
- `action_for_runner(cls)` — 
- `action_for_sl(cls)` — 
- `metrics(rows, pnl_key)` — 
- `bucket(rows, key)` — 
- `compact_examples(rows, sort_key, n)` — 
- `main()` — 
- `avg(k)` — 
- `med(k)` — 

## hermes\scripts\v25\v97_feature_search.py
- `f(x, d)` — 
- `met(rs)` — 
- `bval(r, feat)` — 

## hermes\scripts\v25\v97_sl_autopsy.py
- `f(x, default)` — 
- `kline_path(symbol)` — 
- `pct(n, d)` — 
- `metrics(rows)` — 
- `bucket(rows, key, min_n)` — 
- `replay_sl(row, ks)` — 
- `main()` — 

## hermes\scripts\v25\v97_sl_matrix.py
- `f(x, d)` — 
- `kpath(sym)` — 
- `support_candidates(r, ks)` — 
- `choose_sl(r, ks, mode)` — 
- `simulate(ks, r, sl)` — 
- `metric(results)` — 
- `main()` — 

## hermes\scripts\v25\v97_structural_rr_contract.py
- `f(x, default)` — 
- `confirmed_pivots(ks, end_idx, left, right, kind)` — 
- `equal_high_targets(highs, entry, tol_pct)` — 
- `structural_targets(ks, entry_idx, entry, sl)` — 
- `structural_sl(ks, entry_idx, entry, zone_low)` — 
- `classify(rr2, rr3, has_struct_sl, tp2_type, tp3_type)` — 
- `build_contract(c, ks)` — 
- `simulate(ks, row)` — 
- `summarize(rows)` — 
- `dist(vals)` — 
- `main()` — 

## hermes\scripts\v25\v98_full_entry_exit_autopsy.py
- `num(x, default)` — 
- `date_key(v)` — 
- `year(v)` — 
- `bar_date(b)` — 
- `load_json(path, default)` — 
- `kline_path(symbol)` — 
- `pct(a, b)` — 
- `q(vals, p)` — 
- `stats(rows)` — 
- `entry_bucket(row, ks)` — 
- `exit_bucket(row, ks)` — 
- `bucket_table(rows, key, limit)` — 
- `main()` — 

## hermes\scripts\v25\v98_reachable_5r_probability_gate.py
- `f(x, default)` — 
- `confirmed_pivots(ks, end_idx, left, right, kind)` — 
- `equal_high_targets(highs, entry, tol_pct)` — 
- `structural_targets(ks, entry_idx, entry, sl)` — 
- `structural_sl(ks, entry_idx, entry, zone_low)` — 
- `classify(rr2, rr3, has_struct_sl, tp2_type, tp3_type, pd_zone)` — 
- `build_contract(c, ks)` — 
- `simulate(ks, row)` — 
- `summarize(rows)` — 
- `dist(vals)` — 
- `main()` — 

## hermes\scripts\v25\v98_shadow_fix_matrix.py
- `load(path, default)` — 
- `kline(symbol)` — 
- `n(x, default)` — 
- `yr(r)` — 
- `pct(a, b)` — 
- `stat(rows)` — 
- `by_year(rows)` — 
- `fill_from(ks, start, end, price)` — 
- `rebuild(row, ks, fill_idx, entry_price, variant)` — 
- `runner_reprice(row, ks)` — 
- `main()` — 

## hermes\scripts\v25\v99_economic_autopsy.py
- `f(x, default)` — 
- `load_json(p, default)` — 
- `kline(symbol)` — 
- `rows()` — 
- `stat(rs, fee)` — 
- `sim(row, mode)` — 
- `grouped(rs, field)` — 
- `main()` — 

## hermes\scripts\v25\v99_high_wr_gate_search.py
- `fnum(x, d)` — 
- `year(r)` — 
- `won(r)` — 
- `calc(idx)` — 
- `add(name, fn)` — 

## hermes\scripts\v25\v99_high_wr_production_gate.py
- `fnum(x, default)` — 
- `kline_path(symbol)` — 
- `is_a_v98(r)` — 
- `weak_recovery(r)` — 
- `v99_tier(r)` — 
- `public_grade(tier)` — 
- `apply_frontend_contract(x)` — 
- `simulate_profit_protect(ks, row)` — 
- `normalize_row(r, ks)` — 
- `stats(rows)` — 
- `yearly(rows)` — 
- `field_missing(rows)` — 
- `load_ks_cache(rows)` — 
- `main()` — 

## hermes\scripts\v25\verify_v66_phase2_repairs.py
- `load(path, default)` — 
- `f(v)` — 
- `blank(v)` — 
- `date_key(v)` — 
- `check_pick_file(path, latest_only)` — 
- `check_api(path)` — 
- `main()` — 

## hermes\scripts\v39_prototype.py
- `load_v38_data()` — Load V38.4 full backtest data (stock-level aggregates only)
- `compute_quality_score(stock)` — Compute signal quality score based on stock-level WR/RR.
- `run_backtest(stock_results)` — V39 position sizing backtest using stock-level aggregates.
- `main()` — 

## hermes\scripts\v4_final_report.py

## hermes\scripts\v6_module.py
- `_load(v)` — 
- `_fmt(d)` — 
- `build_v6(nav)` — 
- `build_v6_stock(symbol, nav)` — V6 Stock viewer - redirects back to dashboard with note

## hermes\scripts\v7_module.py
- `fmt_date(d)` — 
- `load_ohlcv(symbol)` — 
- `load_60m(symbol)` — 
- `build_v7(symbol, nav, version)` — Unified K-Line + All Signals + V467/V468 Trades + TP/SL

## hermes\scripts\v9\__init__.py

## hermes\scripts\v9\smc_annotations.py
- `_swing_points(ohlcv, lookback)` — 识别摆动高点和低点。
- `detect_structure_breaks(ohlcv, min_pct)` — 检测BOS(突破结构)和CHoCH(趋势转变)。
- `detect_trend_lines(ohlcv)` — 检测BSL(支撑线), SSL(阻力线), EQL(均衡/中枢线).
- `detect_poi_zones(ohlcv, signals)` — POI由多重信号汇聚形成.
- `detect_supply_demand(ohlcv, volume_mult, kbody_pct)` — Supply/Demand Zone.
- `signals_to_entry_exits(signals, trades, params)` — 将信号和回测交易转化为ECharts entry/exit标记。
- `calc_atr_pct(ohlcv, period)` — 简易ATR计算(百分比)。
- `_render_lines_dict(trend_type, lines_dict, color_fn)` — 将BSL/SSL转为前端可消费的line mark数据。
- `_render_eql_lines(lines)` — EQL均衡线 → ECharts markLine data. [{xAxis, yAxis, ...}]
- `_zones_to_mark_area(zones, color_base, label_prefix)` — 将zone[]转为ECharts markArea格式.
- `generate_chart_data(ohlcv, signals, trades, params)` — 完整的前端ECharts标注数据.

## hermes\scripts\v9\smc_backtest.py
- `_reason_entry(sig, ohlcv, idx, params)` — 生成入场原因描述。
- `_reason_exit(trade_result, bar_idx, exit_bar)` — 生成出场原因描述。
- `_reason_trade_quality(sig, ohlcv, idx)` — 给出交易质量评估。
- `evaluate_trades(ohlcv, params)` — 生成并模拟交易 — 含完整入场/出场原因、信号日志。
- `_format_trade_log(trade)` — 生成单笔交易的人类可读日志。
- `_empty_result(reason)` — 
- `evaluate_params(params, stocks, progress_cb)` — 多股票参数评估 — 保留每只股票的完整交易日志。
- `compute_score(eval_results)` — V9评分 — WR^2.0 + 完整KPI.
- `_max_drawdown(returns)` — 计算最大回撤(%)
- `_zero_score(total_stocks)` — 

## hermes\scripts\v9\smc_config.py
- `get_config_dir()` — Get config directory, create if needed.
- `load_config()` — Load config from YAML, falling back to defaults and env overrides.
- `save_config(config)` — Save config to YAML.
- `get_param_space()` — Get parameter space from config.
- `get_stocks()` — Get stock list from config.
- `get_hubble_config()` — Get Hubble API config.
- `get_config()` — Get cached config (lazy load).
- `reload_config()` — Force reload config from disk.
- `setup_logging()` — Configure logging based on config.

## hermes\scripts\v9\smc_hubble.py
- `hubble_api(endpoint, params, max_retries)` — Call Hubble API with retry and proper error handling.
- `_cache_dir()` — 
- `_cache_path(symbol, period, count)` — 
- `_fetch_kline_from_hubble(symbol, period, count)` — Fetch kline data from Hubble API (V2 endpoint).
- `_get_timestamp(bar)` — Extract timestamp from a bar dict (supports multiple formats).
- `fetch_kline(symbol, period, count)` — Fetch kline data with multi-tier caching.
- `kline_to_ohlcv(kline_data)` — Normalise kline data to standard OHLCV format.
- `calc_atr(ohlcv, period)` — Calculate Average True Range.
- `calc_atr_pct(ohlcv, period)` — Calculate ATR as percentage of current close price.
- `normalize_kline_data(data)` — Alias for kline_to_ohlcv — backward compatibility.
- `fetch_and_prepare(symbol, period, count)` — Fetch kline and convert to OHLCV in one call.

## hermes\scripts\v9\smc_signals.py
- `detect_fvg(ohlcv, min_width, merge_dist)` — Detect Fair Value Gaps (3-candle inefficiency).
- `detect_ifvg(ohlcv, min_width)` — Detect Inverse FVGs — overlapping gap pattern.
- `detect_sweep(ohlcv, lookback, wick_ratio)` — Detect liquidity sweeps — price breaking then reversing.
- `detect_ob(ohlcv, strength_min)` — Detect Order Blocks — last candle before a reversal.
- `detect_bpr(ohlcv, lookback)` — Detect Balanced Price Range — price returns to FVG then reverses.
- `detect_msb(ohlcv, lookback)` — Detect Market Structure Breaks — sustained break of HH/LL.
- `detect_all_signals(ohlcv, params)` — Run all signal detectors and return deduplicated results.
- `score_signal(signal, ohlcv)` — Score a single signal on quality (0-5).
- `signal_summary(signals)` — Summarise detected signals by type and direction.

## hermes\scripts\v9\smc_watchlist.py
- `_hubble_get(endpoint, params, timeout)` — Hubble API GET 请求。
- `_hubble_post(endpoint, body, timeout)` — Hubble API POST 请求。
- `load_cnstock_list(limit)` — 从Hubble加载全部A股列表。
- `load_etf_list(limit)` — 从Hubble加载ETF列表。
- `load_index_list(limit)` — 加载主要指数列表。
- `load_sector_list(limit)` — 加载申万行业板块列表。
- `_scan_symbol(symbol, period, count, params)` — 单只股票信号扫描(带错误处理)。
- `scan_all_markets(limit_stocks, limit_etfs, limit_indices, limit_sectors, callback)` — 全市场信号扫描。
- `run_screen(conditions, page, limit)` — 使用Hubble A股选股筛选器。
- `run_smc_screen()` — SMC专属选股筛选条件: 高换手+放量+Hubble可筛选的条件.
- `build_watch_item(symbol, name, scan_result)` — 从扫描结果构建watchlist item。
- `build_watchlist(market_results, min_score)` — 从全市场扫描结果构建Watchlist。
- `_count_by(items, field)` — 按 field 计数。
- `check_deviations(watchlist_items, threshold_high, threshold_mod)` — 检查所有watchlist项的偏离度。
- `scan_and_build_watchlist(limit_stocks, limit_etfs, limit_indices, limit_sectors, min_score, callback)` — 一键: 扫描全市场 → 构建Watchlist → 检查偏离。
- `_progress(market, symbol, status)` — 

## hermes\scripts\v9\smc_webui.py
- `_proxy_status()` — 
- `_hubble_status()` — 
- `main()` — 

## hermes\scripts\xapi_direct_test.py

## research\asset_inventory.py

## research\aug_pattern.py
- `bars_of(code)` — 

## research\authorize_combo.py

## research\backtest_aug_check.py
- `bars_of(code)` — 

## research\combo_dashboard.py
- `stats(rs)` — 

## research\combo_report.py
- `stats(rs)` — 

## research\combo_v10_run.py
- `bars_of(code)` — 
- `stage_and_deep(bs, i)` — 
- `is_strong(title)` — 
- `r20_of(symbol, entry_date)` — 

## research\combo_v11_final.py
- `bars_of(code)` — 
- `stage_and_deep(bs, i)` — 
- `has_bear_fvg(bs, i, lookback)` — 
- `is_strong(title)` — 
- `r20_of(symbol, entry_date)` — 

## research\combo_v11_run.py
- `bars_of(code)` — 
- `stage_and_deep(bs, i)` — 
- `has_bear_fvg(bs, i, lookback)` — 
- `is_strong(title)` — 
- `r20_of(symbol, entry_date)` — 
- `combo_report(label, smc_leg)` — 

## research\combo_v12_run.py
- `bars_of(code)` — 
- `adx14(bs, i)` — 
- `stage_and_deep(bs, i)` — 
- `has_bear_fvg(bs, i, lookback)` — 
- `is_strong(title)` — 
- `r20_of(symbol, entry_date)` — 
- `combo_report(label, smc_leg)` — 

## research\combo_v12b_run.py
- `bars_of(code)` — 
- `adx14(bs, i)` — 
- `stage_at(bs, i)` — 
- `is_strong(title)` — 
- `stage_and_deep(bs, i)` — 
- `r20_of(symbol, entry_date)` — 

## research\combo_v13_run.py
- `bars_of(code)` — 
- `adx14(bs, i)` — 
- `stage_and_deep(bs, i)` — 
- `has_bear_fvg(bs, i, lookback)` — 
- `is_strong(title)` — 
- `r20_of(symbol, entry_date)` — 

## research\combo_v14_run.py
- `bars_of(code)` — 
- `adx14(bs, i)` — 
- `vol20_at(bs, i)` — 
- `stage_and_deep(bs, i)` — 
- `has_bear_fvg(bs, i, lookback)` — 
- `is_strong(title)` — 
- `r20_of(symbol, entry_date)` — 

## research\combo_v15_run.py
- `bars_of(code)` — 
- `adx14(bs, i)` — 
- `stage_and_deep(bs, i)` — 
- `has_bear_fvg(bs, i, lookback)` — 
- `is_strong(title)` — 
- `r20_of(symbol, entry_date)` — 

## research\combo_v16_run.py
- `bars_of(code)` — 
- `adx14(bs, i)` — 
- `stage_and_deep(bs, i)` — 
- `is_strong(title)` — 
- `r20_of(symbol, entry_date)` — 

## research\combo_v16b_run.py
- `bars_of(code)` — 
- `adx14(bs, i)` — 
- `stage_and_deep(bs, i)` — 
- `has_bear_fvg(bs, i, lookback)` — 
- `is_strong(title)` — 
- `r20_of(symbol, entry_date)` — 

## research\combo_v17_run.py
- `bars_of(code)` — 
- `adx14(bs, i)` — 
- `stage_and_deep(bs, i)` — 
- `is_strong(title)` — 
- `event_leg(hold_non_deep, hold_deep)` — 
- `r20_of(symbol, entry_date)` — 
- `combo_report(label, ev_leg)` — 

## research\combo_v18_run.py
- `bars_of(code)` — 
- `adx14(bs, i)` — 
- `stage_and_deep(bs, i)` — 
- `is_strong(title)` — 
- `r20_of(symbol, entry_date)` — 

## research\combo_v18b_run.py
- `bars_of(code)` — 
- `is_swing_low(bs, j)` — 
- `is_swing_high(bs, j)` — 
- `structural_sltp_wide(bs, i)` — Wider structural SL (min of last 2 swing lows) + TP (highest swing high in lookback).
- `structural_replay(bs, i, ep)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_at(bs, i)` — 
- `report(label, rs)` — 

## research\combo_v18c_run.py
- `bars_of(code)` — 
- `is_swing_high(bs, j)` — 
- `replay_invalidation(bs, i, ep)` — SL = event-day low (signal invalidation), TP = 60d structural high pool.
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_at(bs, i)` — 
- `report(label, rs)` — 

## research\combo_v18d_run.py
- `bars_of(code)` — 
- `is_swing_high(bs, j)` — 
- `replay_hybrid(bs, i, ep)` — Hold up to HOLD_CAP; exit early at structural TP; SL = event low * 0.98.
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_at(bs, i)` — 
- `report(label, rs)` — 

## research\combo_v19_run.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_detailed(bs, i)` — 
- `report(label, rs)` — 

## research\combo_v19b_run.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_detailed(bs, i)` — 
- `report(label, rs)` — 

## research\combo_v19c_run.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_detailed(bs, i)` — 
- `report(label, rs)` — 

## research\combo_v20_run.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_detailed(bs, i)` — 
- `report(label, rs)` — 

## research\combo_v20b_run.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_detailed(bs, i)` — 
- `report(label, rs)` — 

## research\combo_v20c_run.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_detailed(bs, i)` — 
- `report(label, rs)` — 

## research\combo_v21_run.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_detailed(bs, i)` — 
- `report(label, rs)` — 

## research\combo_v2_run.py
- `bars_of(symbol)` — 
- `r20_of(symbol, entry_date)` — 
- `is_strong(title)` — 
- `strong_events(hold)` — 

## research\combo_v3_run.py
- `r20_of(symbol, entry_date)` — 
- `bars_of(symbol)` — 
- `vwap_dev(symbol, entry_date)` — 
- `is_strong(title)` — 
- `ev_bars(code)` — 

## research\combo_v4_run.py
- `bars(path)` — 
- `dna_at(symbol, entry_date)` — 
- `r20_of(symbol, entry_date)` — 
- `is_strong(title)` — 
- `ev_bars(code)` — 
- `combo_report(label, smc_leg)` — 

## research\combo_v5_run.py
- `bars(path)` — 
- `agg(daily, key_fn)` — 
- `trend_state(agg_bars, ref_key, win)` — 
- `mw_states(symbol, entry_date)` — 
- `r20_of(symbol, entry_date)` — 
- `is_strong(title)` — 
- `ev_bars(code)` — 

## research\combo_v6_run.py
- `bars(path)` — 
- `stage_at(symbol, entry_date)` — 
- `r20_of(symbol, entry_date)` — 
- `is_strong(title)` — 
- `ev_bars(code)` — 

## research\combo_v7_run.py
- `bars(path)` — 
- `stage_at_idx(bs, i)` — 
- `is_steady(symbol, entry_date, lookback)` — 
- `r20_of(symbol, entry_date)` — 
- `is_strong(title)` — 
- `ev_bars(code)` — 

## research\combo_v8_run.py
- `bars_of(code)` — 
- `stage_at(bs, i)` — 
- `is_strong(title)` — 
- `r20_of(symbol, entry_date)` — 
- `stage_at_sym(symbol, entry_date)` — 

## research\combo_v9_run.py
- `bars_of(code)` — 
- `stage_and_depth(bs, i)` — Return (stage, is_deep). stage: ACCUM/DOWNTREND/UPTREND/MARKUP/DISTRIB.
- `is_strong(title)` — 
- `r20_of(symbol, entry_date)` — 

## research\confirm_final.py

## research\consistency_check.py
- `check(name, ok, detail)` — 

## research\continuation_scanner.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_detailed(bs, i)` — 
- `compute_median()` — 

## research\corrected_detailed.py
- `load()` — 
- `_stats(vals)` — 
- `main()` — 
- `_gather(key, gk_func)` — 

## research\current_scanner.py
- `bars(path)` — 
- `market_latest()` — Determine latest trading date from Sina realtime (authoritative).
- `refresh_key_stocks()` — Force-refresh holdings + recent-event stocks from Sina (small set, fast serial).
- `scan_one(p, latest)` — 

## research\daily_combo_run.py
- `run(script)` — 
- `_pause_monitor()` — FIX(2026-08-22): stop realtime monitor loop during daily run — concurrent Sina polling
- `_resume_monitor()` — 
- `main()` — 

## research\data_health_check.py
- `check_source(name, url, timeout)` — 

## research\debug_lhb.py

## research\deep_robustness.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `test(label, ret_th, vt_th)` — 

## research\exec_quality_audit.py
- `bars(path)` — 
- `med(vals)` — 
- `audit_smc()` — SMC leg entry/exit quality.
- `audit_event(limit)` — Event leg entry/exit quality.
- `get_bars(sym)` — 
- `bars_of(code)` — 
- `is_strong(title)` — 

## research\exec_quality_event.py
- `bars_of(code)` — 
- `is_strong(title)` — 

## research\exec_quality_history.py
- `bars_of(code)` — 
- `med(vals)` — 
- `audit_trades(trades, label)` — For each trade, entry vs prev-close gap, entry-day low, exit vs peak.

## research\exec_quality_smc.py
- `bars(path)` — 
- `get_bars(sym)` — 

## research\exec_quality_v17.py
- `bars_of(code)` — 
- `med(vals)` — 

## research\exec_quality_v18.py
- `bars_of(code)` — 
- `med(vals)` — 

## research\exec_quality_v20.py
- `bars_of(code)` — 
- `med(vals)` — 
- `audit(label, pool, hold_ref)` — 

## research\expA_regime.py
- `bars(path)` — 

## research\expB_regime_filter.py
- `regime_at(entry_date)` — 
- `year_of(t)` — 

## research\expC_2026_deep.py

## research\expD_breadth.py
- `breadth_at(entry_date)` — 

## research\expE_pullback.py
- `prior_ret(symbol, entry_date)` — 
- `report(label, rs)` — 

## research\expF_market_protect.py
- `r20_of(symbol, entry_date)` — 
- `mkt_at(entry_date)` — 

## research\final_inventory.py

## research\finalize_dashboard.py

## research\finalize_v20d.py
- `stats(rs)` — 

## research\finalize_v20e.py
- `stats(rs)` — 

## research\finalize_v20f.py
- `stats(rs)` — 

## research\gen_code_map.py
- `extract(path)` — 返回 {funcs: [...], classes: [...]}

## research\gen_cont_v20f.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_of(bs, i)` — 

## research\gen_v20d.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 

## research\gen_v20e.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `weekly_trend_of(bs, i)` — 

## research\gen_v20f.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `weekly_trend_of(bs, i)` — 

## research\incremental_batch_refresh.py
- `stale_files(latest)` — Files whose last bar date < latest trading date (need refresh).
- `main()` — 

## research\iter_2025_decomp.py
- `stats(rs)` — 

## research\iter_60min.py
- `bars(path)` — 
- `bars60(path)` — 
- `is_swing_low(ks, j, p)` — 
- `fwd_pnl(symbol, entry_date, hold)` — 

## research\iter_accum_combo.py
- `bars_of(code)` — 
- `stage_of(bs, i)` — 
- `report(label, rs)` — 
- `score(t)` — 0/1: ACCUM stage priority for EVENT; low-vol for CONT.

## research\iter_accum_depth.py
- `bars_of(code)` — 
- `accum_depth(bs, i)` — Return depth level at bar i: DEEP / MID / SHALLOW / None(non-accum).
- `is_strong(title)` — 
- `report(label, rs)` — 

## research\iter_accum_rank.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_and_info(bs, i)` — Return (stage, deep, vol20) for ranking.
- `report(label, rs)` — 

## research\iter_accum_triple.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `report(label, rs)` — 

## research\iter_accumvol_combo.py
- `bars_of(code)` — 
- `stage_of(bs, i)` — 
- `report(label, rs)` — 

## research\iter_adaptive.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_at(bs, i, win)` — 

## research\iter_adx_combo.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `event_leg(adx_min)` — 
- `combo(ev)` — 
- `report(label, rs)` — 

## research\iter_adx_v18.py
- `bars(path)` — 
- `adx14(bs, i)` — 
- `get_bars(sym)` — 
- `report(label, rs)` — 

## research\iter_behavior_dna.py
- `bars(path)` — 
- `behavior_at(symbol, entry_date)` — Return behavior signature dict (PIT, entry-60d window).
- `r20_of(symbol, entry_date)` — 
- `report(label, rs)` — 

## research\iter_bigmoney.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `report(label, rs)` — 

## research\iter_blocktrade.py
- `bars_of(code)` — 
- `build(prem_max, amt_min)` — 
- `report(label, rs)` — 

## research\iter_boot_final.py

## research\iter_boot_v20d.py

## research\iter_breakout.py
- `bars(path)` — 
- `is_swing_high(bs, j)` — 
- `is_swing_low(bs, j)` — 
- `stage_detailed(bs, i)` — 
- `build_breakout(sym, daily)` — ACCUM (bottom accumulation) -> close breaks recent swing high (BOS start)
- `replay(seed, daily)` — 
- `report(label, rs)` — 

## research\iter_breakout_exec.py
- `bars(path)` — 
- `is_swing_high(bs, j)` — 
- `is_swing_low(bs, j)` — 
- `stage_detailed(bs, i)` — 
- `replay_tp2(sig)` — 
- `report(label, rs)` — 

## research\iter_bsl_sweep.py
- `f(x, d)` — 
- `bars(path)` — 
- `is_swing_high(ks, j)` — 
- `is_swing_low(ks, j)` — 
- `build_bsl_seeds(sym, daily)` — BSL sweep: poke above confirmed swing high, close below; pullback to demand OB; reclaim; e
- `replay(seed, daily)` — 
- `get_bars(sym)` — 

## research\iter_bsl_v2.py
- `f(x, d)` — 
- `bars(path)` — 
- `is_swing_high(ks, j)` — 
- `is_swing_low(ks, j)` — 
- `build_bsl_filtered(sym, daily)` — BSL sweep + response + demand OB + reclaim + entry, with r20 + stage filters.
- `replay(seed, daily)` — 

## research\iter_buy_exec.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `open_entry()` — 
- `retrace_entry(discount)` — 限价单：挂披露日收盘价（×discount），T+1 最低<=挂单价则成交（挂单价），否则开盘买
- `low_entry()` — 
- `report(label, rs)` — 

## research\iter_choch.py
- `f(x, d)` — 
- `bars(path)` — 
- `is_swing_low(ks, j)` — 
- `is_swing_high(ks, j)` — 
- `build_choch(sym, daily)` — CHOCH: after a down-swing, close breaks the most recent swing high (structure shift),
- `replay(seed, daily)` — 

## research\iter_combo_ranking.py
- `bars_of(code)` — 
- `score_trade(t)` — Unified quality score: EVENT deep+vol / SMC fvg / CONT low-vol.
- `report(label, rs)` — 

## research\iter_compliance.py

## research\iter_cont_buy.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_of(bs, i)` — 
- `collect_signals()` — 
- `sim(entry_mode)` — 
- `report(label, rs)` — 

## research\iter_cont_curve.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_detailed(bs, i)` — 

## research\iter_cont_ev30.py
- `bars_of(code)` — 
- `report(label, rs)` — 

## research\iter_cont_event.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_detailed(bs, i)` — 
- `report(label, rs)` — 

## research\iter_cont_execution.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `is_swing_high(bs, j)` — 
- `stage_detailed(bs, i)` — 
- `collect_signals()` — Collect MARKUP+struct+vwap5% signals with entry_idx/entry/sl/tp_swing for replay variants.
- `replay_tp2(sig)` — 
- `replay_hold(sig, hold)` — 
- `replay_struct(sig)` — Structural: TP = swing high, SL = support low, MSS trailing.
- `report(label, rs)` — 

## research\iter_cont_hold.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_detailed(bs, i)` — 
- `report(label, rs)` — 

## research\iter_cont_mss.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_detailed(bs, i)` — 
- `report(label, rs)` — 

## research\iter_cont_params.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_of(bs, i)` — 
- `run_cont(VWAP_MIN, VOL_MAX, ADX_MIN, limit)` — 
- `report(label, rs)` — 

## research\iter_cont_sens.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_of(bs, i)` — 
- `report(label, sigs)` — 

## research\iter_cont_strength.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_and_ret60(bs, i)` — 
- `report(label, rs)` — 

## research\iter_cont_tiered.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `is_swing_high(bs, j)` — 
- `stage_of(bs, i)` — 
- `collect_signals()` — 
- `fixed_hold(hold)` — 
- `tiered()` — 
- `report(label, rs)` — 

## research\iter_cont_timing.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_of(bs, i)` — 

## research\iter_cont_verify.py

## research\iter_cont_vol.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_detailed(bs, i)` — 
- `report(label, rs)` — 

## research\iter_cont_vwap_th.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_detailed(bs, i)` — 
- `report(label, rs)` — 

## research\iter_cont_weekday.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_detailed(bs, i)` — 
- `report(label, rs)` — 

## research\iter_continuation_deep.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_detailed(bs, i)` — 
- `report(label, rs)` — 

## research\iter_continuation_variants.py
- `bars(path)` — 
- `ma(bs, i, n)` — 
- `adx14(bs, i)` — 
- `is_swing_low(bs, j)` — 
- `stage(bs, i)` — 
- `scan(variant)` — variant: which MA/condition to use.
- `report(label, rs)` — 

## research\iter_crown_2024.py

## research\iter_crown_check.py

## research\iter_deep_threshold.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_detailed(bs, i)` — 
- `report(label, rs)` — 
- `run(deep_ret, hold)` — 

## research\iter_deep_vol.py
- `bars_of(code)` — 
- `adx14(bs, i)` — 
- `stage_at(bs, i)` — 
- `is_strong(title)` — 
- `report(label, rs)` — 

## research\iter_density_ret.py
- `avg(x)` — 

## research\iter_dna_bucket.py
- `bars(path)` — 
- `dna_at(symbol, entry_date)` — 
- `r20_of(symbol, entry_date)` — 
- `report(label, rs)` — 

## research\iter_dna_window.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_at(bs, i, win)` — 

## research\iter_double_sweep.py
- `f(x, d)` — 
- `bars(path)` — 
- `is_swing_low(ks, j)` — 
- `is_swing_high(ks, j)` — 
- `build_double_sweep(sym, daily)` — 
- `replay(seed, daily)` — 

## research\iter_entry_mode.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_at(bs, i)` — 
- `report(label, rs)` — 

## research\iter_entry_modes.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 

## research\iter_entry_premium.py
- `bars_of(code)` — 
- `is_strong(title)` — 

## research\iter_etype_tpsl.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `ev_type(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `report(label, rs)` — 

## research\iter_ev_perf.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_and_deep(bs, i)` — 
- `report(label, rs)` — 

## research\iter_ev_smc_resonance.py
- `bars(path)` — 
- `stage_detailed(bs, i)` — 
- `report(label, rs)` — 

## research\iter_event_adx.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `report(label, rs)` — 

## research\iter_event_continuation.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_and_vwap(bs, i)` — 
- `report(label, rs)` — 

## research\iter_event_curve.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_and_deep(bs, i)` — 

## research\iter_event_delay.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_and_deep(bs, i)` — 
- `report(label, rs)` — 

## research\iter_event_dna.py
- `bars_of(code)` — 
- `stage_at(bs, i)` — 
- `is_strong(title)` — 
- `report(label, rs)` — 

## research\iter_event_entry.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_at(bs, i)` — 
- `run(entry_offset, hold)` — entry_offset: 0=T+1 open, 1=T+1 close, 2=T+2 open. hold bars after entry.

## research\iter_event_hold2.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_and_deep(bs, i)` — 
- `report(label, nd, dp)` — 

## research\iter_event_newinfo.py
- `bars_of(code)` — 
- `is_new_info(title)` — 首次/方案/计划（新信息）—— 排除进展/完成/进度/前十名
- `adx14(bs, i)` — 
- `stage_and_deep(bs, i)` — 
- `event_leg(mode)` — mode: 'full' (含进展) or 'new' (只首次/方案)
- `report(label, rs)` — 

## research\iter_event_range.py
- `bars_of(code)` — 
- `adx14(bs, i)` — 
- `is_strong(title)` — 
- `stage_at(bs, i)` — 
- `report(label, rs)` — 

## research\iter_event_ranking.py
- `bars_of(code)` — 
- `adx14(bs, i)` — 
- `stage_and_deep(bs, i)` — 
- `is_strong(title)` — 
- `run_top(pct)` — 

## research\iter_event_split.py
- `bars_of(symbol)` — 
- `trades_for(q, hold)` — 
- `yearly(rows)` — 

## research\iter_event_stage.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `report(label, rs)` — 

## research\iter_event_subtype.py
- `bars_of(code)` — 
- `adx14(bs, i)` — 
- `stage_and_deep(bs, i)` — 
- `classify_type(title)` — 
- `report(label, rs)` — 

## research\iter_event_switch.py
- `bars_of(code)` — 
- `stage_at(bs, i, win)` — 
- `switch_type(bs, i, lookback)` — Stage at entry vs stage lookback bars ago. Return (type) or None.
- `is_strong(title)` — 
- `report(label, rs)` — 

## research\iter_event_type.py
- `bars_of(code)` — 
- `adx14(bs, i)` — 
- `stage_and_deep(bs, i)` — 
- `classify(title)` — 
- `report(label, rs)` — 

## research\iter_event_vol.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_and_deep(bs, i)` — 
- `report(label, rs)` — 

## research\iter_exec_audit.py

## research\iter_exit_calc.py

## research\iter_exit_modes.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `fixed_hold(hold)` — 
- `tiered(tp1_frac)` — 
- `trailing(stop_pct, hold)` — 移动止损：从最高点回撤 stop_pct 平仓（或持有到期）
- `report(label, rs)` — 

## research\iter_exit_preview.py

## research\iter_exit_price.py

## research\iter_fee_sensitivity.py
- `report(label, rs)` — 

## research\iter_final_combo.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_of(bs, i)` — 
- `cont_leg(vwap_min)` — 
- `report(label, rs)` — 

## research\iter_final_rank.py
- `bars_of(code)` — 
- `stage_and_info(bs, i)` — 
- `report(label, rs)` — 

## research\iter_final_rank2.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `weekly_trend_of(bs, i)` — 
- `report(label, rs)` — 

## research\iter_fvg.py
- `bars(path)` — 
- `has_bullish_fvg(daily, i, lookback)` — bullish FVG (gap) within lookback bars before i: low[k] > high[k-2].
- `has_bearish_fvg(daily, i, lookback)` — bearish FVG: high[k] < low[k-2] (gap above, supply) - noise signal.
- `get_bars(sym)` — 
- `run(label, filt)` — 

## research\iter_hold_depth.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `is_deep(bs, i)` — 
- `pnl_at(e, hold)` — 

## research\iter_idx_filter.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `idx_state(d)` — index state at date d: above/below MA20, oversold(5d<-5%)
- `report(label, rs)` — 

## research\iter_leg_corr.py
- `corr(a, b)` — 

## research\iter_lhb_backtest.py
- `bars_of(code)` — 
- `build_trades(threshold)` — 
- `report(label, rs)` — 

## research\iter_lhb_signal.py
- `bars_of(code)` — 
- `check(inst_net)` — Signal: institutional net buy > threshold. Entry next open, hold 10d.

## research\iter_lhb_verify.py
- `report(label, rs)` — 

## research\iter_margin_check.py

## research\iter_mark_trend.py

## research\iter_marketcap.py
- `bars_of(code)` — 
- `price_band(t)` — Proxy market cap via price at entry (low price = small cap typical).
- `report(label, rs)` — 

## research\iter_metric_audit.py

## research\iter_mon_vol.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_and_deep(bs, i)` — 
- `report(label, rs)` — 

## research\iter_monthly.py
- `bars(path)` — 
- `monthly_agg(daily)` — Aggregate daily -> monthly bars (YYYYMM).
- `monthly_permission(months, day_date)` — Monthly trend: last 3 monthly bars form rising structure (HH/HL) OR at least
- `monthly_bsl(months, day_date, minimum)` — Monthly BSL (liquidity pool high) before current month, above minimum.
- `get_bars(sym)` — 
- `run(label, filt)` — 

## research\iter_monthly2.py
- `bars(path)` — 
- `monthly_agg(daily)` — 
- `monthly_perm(months, day_date)` — 
- `monthly_ok(symbol, entry_date)` — 
- `report(label, rs)` — 

## research\iter_monthly_adaptive.py
- `bars(path)` — 
- `monthly_agg(daily)` — 
- `monthly_state(months, day_date)` — Return 'WEAK' (no HH/HL, close below mid) or 'STRONG'.
- `state_of(symbol, entry_date)` — 
- `r20_of(symbol, entry_date)` — 
- `report(label, rs)` — 

## research\iter_monthly_update.py

## research\iter_mss_horizon.py
- `load_bars(path)` — 
- `detect_mss_bull(bs, i)` — 

## research\iter_mss_verify.py
- `load_bars(path)` — 
- `detect_mss_bull(bs, i)` — 

## research\iter_mtf_weekly.py
- `bars(path)` — 
- `weekly_file(sym)` — 
- `weekly_up(filepath, entry_date)` — Weekly trend up: last weekly close above 12-week MA (weekly uptrend).
- `is_swing_low(bs, j)` — 
- `stage_detailed(bs, i)` — 
- `report(label, rs)` — 

## research\iter_multi_rank.py
- `bars_of(code)` — 
- `score_full(t)` — Multi-feature score per leg.
- `report(label, rs)` — 

## research\iter_multi_rank2.py
- `bars_of(code)` — 
- `score_v2(t)` — V2 score: EVENT monday+perf+deep / CONT lowvol+monday / SMC fvg.
- `report(label, rs)` — 

## research\iter_multiperiod.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `weekly_trend(bs, i)` — 周线趋势：按 5 日聚合周线，MA10 周线上/下行
- `report(label, rs)` — 

## research\iter_nolookahead_rank.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `weekly_trend_of(bs, i)` — 
- `report(label, rs)` — 

## research\iter_path.py
- `bars_of(code)` — 
- `is_strong(title)` — 

## research\iter_perf.py
- `bars_of(code)` — 
- `is_perf(title)` — 
- `report(label, rs)` — 

## research\iter_plan_mon.py
- `bars_of(code)` — 
- `is_strong_new(title)` — 首次/方案/计划（新信息）+ 排除进展/完成/进度/前十名
- `adx14(bs, i)` — 
- `stage_and_deep(bs, i)` — 
- `report(label, rs)` — 

## research\iter_range_skip.py
- `bars(path)` — 
- `adx14(daily, i)` — Simplified ADX(14) at bar i (PIT). Returns None if insufficient.
- `get_bars(sym)` — 
- `report(label, rs)` — 

## research\iter_resonance.py
- `bars(path)` — 
- `agg(daily, key_fn)` — 
- `trend_state(agg_bars, ref_key, win)` — Rising state: last win bars HH/HL.
- `states_at(symbol, entry_date)` — 
- `r20_of(symbol, entry_date)` — 
- `report(label, rs)` — 

## research\iter_retrace_exec.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 

## research\iter_sequence.py
- `day_diff(a, b)` — 
- `report(label, rs)` — 

## research\iter_sequence2.py
- `bars(path)` — 
- `day_diff(a, b)` — 
- `report(label, rs)` — 

## research\iter_signal_order.py

## research\iter_sl_dist2.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 

## research\iter_sl_hybrid.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `atr14(bs, i)` — 
- `sim(sl_mode, atr_mult)` — 
- `report(label, rs)` — 

## research\iter_slippage.py
- `report(label, rs)` — 

## research\iter_smc_accuracy.py
- `load_bars(path)` — 

## research\iter_smc_audit.py
- `is_swing_low_old(ks, j)` — 
- `is_swing_high_old(ks, j)` — 
- `is_swing_low_new(ks, j)` — 
- `is_swing_high_new(ks, j)` — 
- `sweep_signals(daily, swing_lows, sweep_pct, is_sw_func)` — Count sweep + BOS signals per stock.

## research\iter_smc_confirm.py
- `load_bars(path)` — 

## research\iter_smc_continuation.py
- `bars(path)` — 
- `ma20(bs, i)` — 
- `is_swing_low(bs, j)` — 
- `build_continuation(sym, daily)` — UPTREND/MARKUP + retrace to MA20 (low <= MA20) + close reclaim above MA20 -> next open ent
- `replay(seed, daily)` — 
- `report(label, rs)` — 

## research\iter_smc_curve.py
- `bars(path)` — 
- `stage_detailed(bs, i)` — 

## research\iter_smc_entry_mode.py
- `bars(path)` — 
- `is_swing_high(bs, j)` — 
- `stage_detailed(bs, i)` — 
- `vwap5_ok(bs, i)` — 
- `report(label, rs)` — 

## research\iter_smc_hold.py
- `bars(path)` — 
- `stage_at(bs, i)` — 
- `r20_of(symbol, entry_date)` — 
- `fwd(symbol, entry_date, hold)` — 

## research\iter_smc_hold2.py
- `load_bars(path)` — 
- `detect_mss_bull(bs, i)` — 
- `simulate(max_hold)` — 

## research\iter_smc_large.py
- `load_bars(path)` — 

## research\iter_smc_param_cmp.py
- `run_all(limit)` — Run SMC reversal leg with current params; returns trades.
- `report(label, trades)` — 

## research\iter_smc_param_cmp2.py
- `run_all(limit)` — 
- `report(label, trades)` — 

## research\iter_smc_ranking.py
- `bars(path)` — 
- `get_bars(sym)` — 
- `report(label, rs)` — 

## research\iter_smc_stability.py
- `load_bars(path)` — 

## research\iter_smc_supply.py
- `bars_of(code)` — 
- `adx14(bs, i)` — 
- `stage_at(bs, i)` — 
- `has_bear_fvg(bs, i, lookback)` — 
- `r20_of(symbol, entry_date, hi)` — 
- `report(label, rs)` — 

## research\iter_smc_vol.py
- `bars(path)` — 
- `stage_detailed(bs, i)` — 
- `report(label, rs)` — 

## research\iter_smc_weekday.py
- `bars(path)` — 
- `stage_detailed(bs, i)` — 
- `report(label, rs)` — 

## research\iter_span_combo.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `report(label, rs)` — 

## research\iter_span_return.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `report(label, rs)` — 

## research\iter_stage_window.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i, window)` — 
- `run(window)` — 
- `report(label, rs)` — 

## research\iter_state_exec.py
- `bars(path)` — 
- `monthly_agg(daily)` — 
- `monthly_state(months, day_date)` — 
- `state_of(symbol, entry_date)` — 
- `fwd_pnl(symbol, entry_date, hold)` — 

## research\iter_strong_events.py
- `bars_of(symbol)` — 
- `is_strong(title)` — 
- `run(label, strong_only, hold)` — 

## research\iter_strong_filter.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `market_proxy(d8)` — 
- `report(label, rs)` — 

## research\iter_struct_confirm.py
- `bars_of(symbol)` — 
- `get_all_events()` — 
- `structure_ok(bs, entry_idx)` — price-structure confirmation at entry: close above 20d MA and MA rising.
- `run(filters, label, hold)` — 

## research\iter_structure_support.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_detailed(bs, i)` — 
- `report(label, rs)` — 

## research\iter_subspan.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 

## research\iter_sweep_depth.py
- `bars(path)` — 
- `sweep_depth(daily, i, swept)` — How deep the sweep went below the SSL swing low (%).
- `get_bars(sym)` — 
- `report(label, rs)` — 

## research\iter_sweep_large.py
- `load_bars(path)` — 

## research\iter_swing_quality.py
- `bars(path)` — 
- `is_swing_low_consensus(ks, j)` — swing low confirmed at multiple lookbacks: 3/3 and 5/5 both confirm.
- `build_consensus_seeds(sym, daily)` — Same main line as build_seeds but swing lows require 3/3 AND 5/5 consensus.
- `get_bars(sym)` — 

## research\iter_switch.py
- `bars(path)` — 
- `stage_at_idx(bs, i)` — stage at bar index i (60d window ending at i-1, PIT).
- `switch_info(symbol, entry_date, lookback)` — Was there a stage switch within lookback bars before entry? Return (switched, from, to).
- `r20_of(symbol, entry_date)` — 
- `report(label, rs)` — 

## research\iter_tier_trigger.py

## research\iter_tiered_backtest.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `fixed_hold(ev, hold)` — 
- `tiered_exit(ev)` — 
- `report(label, rs)` — 

## research\iter_tiered_frac.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `tiered(ev, tp1_frac)` — 
- `report(label, rs)` — 

## research\iter_tiers_final.py
- `stats(rs)` — 
- `report(label, rs)` — 

## research\iter_tp1_after.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 

## research\iter_tp1_dist.py

## research\iter_tp2_after.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 

## research\iter_tp_range.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `report(label, rs)` — 

## research\iter_tp_structure.py
- `replay_tp2_cfg(seed, daily, tp1_frac, tp2_mult)` — 
- `run_cfg(tp1_frac, tp2_mult, limit)` — 
- `report(label, trades)` — 

## research\iter_trend_continuation.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_and_ret(bs, i)` — 
- `report(label, rs)` — 

## research\iter_triple_filter.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `weekly_trend(bs, i)` — 
- `report(label, rs)` — 

## research\iter_type_verify.py

## research\iter_ultimate.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `weekly_trend_of(bs, i)` — 
- `tiered_exit(e, ep)` — 
- `run(rank_min, retrace)` — 
- `report(label, rs)` — 

## research\iter_v20d_plus.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `run(mode)` — 
- `tiered_exit(e, ep)` — 
- `report(label, rs)` — 

## research\iter_v20d_tiered.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `report(label, rs)` — 

## research\iter_vol_cont.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `report(label, rs)` — 

## research\iter_vol_tier.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `report(label, rs)` — 

## research\iter_volume.py
- `bars(path)` — 
- `get_bars(sym)` — 
- `run(label, filt)` — 

## research\iter_vwap.py
- `bars(path)` — 
- `rolling_vwap(daily, idx, window)` — 20-day rolling VWAP at bar idx (uses idx and prior bars, PIT).
- `r20_of(symbol, entry_date)` — 
- `vwap_at(symbol, entry_date)` — 
- `report(label, rs)` — 
- `entry_close(symbol, entry_date)` — 

## research\iter_vwap_combo.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_of(bs, i)` — 
- `cont_leg(VWAP_MIN, limit)` — 
- `report(label, rs)` — 
- `combo(cont)` — 

## research\iter_vwap_threshold.py
- `bars_of(code)` — 
- `adx14(bs, i)` — 
- `stage_and_deep(bs, i)` — 
- `is_strong(title)` — 
- `r20_of(symbol, entry_date)` — 
- `smc_leg(vwap_th)` — 
- `combo_report(label, smc_leg)` — 

## research\iter_vwap_v17.py
- `bars(path)` — 
- `vwap_dev(bs, i)` — 20d rolling VWAP deviation at entry bar (PIT).
- `get_bars(sym)` — 
- `report(label, rs)` — 

## research\iter_weak_market.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_of(bs, i)` — 
- `market_proxy(d8)` — 
- `report(label, rs)` — 

## research\iter_weekday.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `adx14(bs, i)` — 
- `stage_and_deep(bs, i)` — 
- `report(label, rs)` — 

## research\iter_weekly_bug.py
- `iso_weeks(daily)` — 

## research\iter_weekly_cmp.py
- `iso_aggregate(daily)` — 
- `run_all(weekly_mode, limit)` — 
- `report(label, trades)` — 

## research\iter_weight.py
- `report(label, rs, weight_map)` — rs: list of (t, w) tuples.

## research\iter_zone_age.py
- `bars(path)` — 
- `day_diff(a, b)` — 
- `get_bars(sym)` — 
- `report(label, rs)` — 

## research\migrate_ledger.py

## research\monthly_risk_calendar.py

## research\p0_freeze.py

## research\p0_src_fix.py

## research\p1_rank_backfill.py

## research\p2_audit2.py

## research\p2_cont_refresh.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_of(bs, i)` — 

## research\p2_crown_report.py

## research\p2_smc_restore.py

## research\paper_adjudicate.py
- `adjudicate(target_date)` — Close OPEN positions whose expiry <= target_date at close price.
- `main()` — 

## research\paper_loss_analysis.py

## research\paper_loss_struct.py

## research\paper_sim.py
- `load_ledger()` — 
- `save_ledger(led)` — 
- `realtime_prices(codes)` — Fetch realtime current prices for codes (up to ~50 per request).
- `sub_signals_event(bs, i, sig_date)` — Event-leg sub-signals: 阶段确认日 / ADX≥20 确认日 / 披露日 / 入场日.
- `sub_signals_cont(bs, entry_idx, support_date)` — Continuation-leg sub-signals: MARKUP 确认 / 支撑回踩 / VWAP≥5% / 入场.
- `stage_and_deep(bs, i)` — Behavior stage + DEEP flag (backtest-consistent quality filter, FIX 2026-08-22).
- `weekly_trend_of(bs, i)` — 周线趋势（5日聚合周线，MA10 周线上/下行）—— 研究：周线 down 事件 +7.50% vs up +1.00%
- `_market_proxy(code)` — 计算给定股票 signal 日期的市场状态（200 只采样 20 日平均涨跌，决策时点可得）
- `adaptive_hold(base_hold, proxy)` — 
- `adx14_of(bs, i)` — 
- `bars_of(code)` — 
- `is_swing_high(bs, j)` — 
- `is_swing_low(bs, j)` — 
- `structural_sltp(code, signal_date, src, stage, adx)` — SMC 策略化结构分层 TP/SL —— 锚点指标按信号类型/行为阶段动态选择（非固定映射）。
- `daily_selection()` — Scan new insider events -> create PENDING_ORDER entries.
- `_append_realtime_log(snapshot)` — Append price snapshot to realtime_log.json (keep last 2000).
- `_append_trade_log(rec)` — 记录交易日志（买入/卖出）—— 时间/信号/动作/TP/SL/触发类型/盈亏
- `realtime_monitor()` — Check pending orders (price<=entry -> FILLED) and filled (TP/SL -> CLOSED).

## research\paper_tracker.py
- `bars_of(code)` — 
- `load(name, default)` — 
- `save(name, data)` — 
- `main()` — 
- `stage_of(code, i)` — 
- `deep_of(code, i)` — 
- `adx14_of(code, i)` — 
- `vol20_of(code, i)` — 

## research\portfolio_combo.py
- `r20_of(symbol, entry_date)` — 
- `bars_of(symbol)` — 
- `event_trade(symbol, event_date, hold)` — 

## research\r20_scan.py
- `bars(path)` — 

## research\r20_scan2.py
- `r20_of(symbol, entry_date)` — 

## research\refresh_then_select.py
- `run_script(script)` — 
- `batch_refresh_worker(batch_size)` — 后台分批刷新：循环刷新 stale 文件，直到没有或截止时间到。
- `main()` — 

## research\register_combo.py

## research\rollback_v13.py
- `stats(rs)` — 

## research\sensitivity_hold.py
- `bars_of(symbol)` — 
- `event_trades(hold)` — 
- `yearly(rows)` — 

## research\sim_scheduler.py
- `daily()` — 
- `loop_once()` — 
- `main()` — 

## research\smc_monthly_calendar.py
- `monthly(pool)` — 

## research\style_risk.py
- `bars_of(code)` — 

## research\top50_audit.py
- `bars_of(code)` — 
- `score_trade(t)` — 

## research\tp2_r20_oracle.py
- `bars(path)` — 
- `oracle_events(sym, ks)` — Independent re-derivation (different code path, same semantics):
- `load_seed_ids(csv_path)` — 
- `main()` — 
- `plow(j)` — 

## research\tp2_r20_run.py
- `bars(path)` — 

## research\update_v2.py
- `stats(rs)` — 

## research\upgrade_v16b.py
- `stats(rs)` — 

## research\v10_contract_audit.py

## research\v10_finalize.py
- `stats(rs)` — 

## research\v10_robustness.py
- `bars_of(code)` — 
- `is_strong(title)` — 
- `get_events(ret_th, vt_th, hold_deep, hold_std, stage_keep)` — Return event trades under given deep-threshold + hold policy.
- `combo_report(ev)` — 

## research\v11_finalize.py
- `stats(rs)` — 

## research\v11_robustness.py
- `bars_of(code)` — 
- `stage_at(bs, i)` — 
- `has_bear_fvg(bs, i, lookback)` — 
- `r20_of(symbol, entry_date)` — 
- `smc_leg(lookback)` — 
- `report(rs)` — 

## research\v13_audit.py
- `yearly_detail(label, pool)` — 

## research\v13_finalize.py
- `stats(rs)` — 

## research\v13_prep.py

## research\v13_robustness.py
- `bars_of(code)` — 
- `adx14(bs, i)` — 
- `stage_at(bs, i)` — 
- `is_strong(title)` — 
- `r20_of(symbol, entry_date)` — 
- `run(th)` — 

## research\v14_audit.py

## research\v14_fairness.py
- `bars_of(code)` — 
- `adx14(bs, i)` — 
- `vol20_at(bs, i)` — 
- `stage_at(bs, i)` — 
- `is_strong(title)` — 

## research\v14_finalize.py
- `stats(rs)` — 

## research\v14_robustness.py
- `bars_of(code)` — 
- `adx14(bs, i)` — 
- `vol20_at(bs, i)` — 
- `stage_at(bs, i)` — 
- `is_strong(title)` — 
- `run(pct)` — 

## research\v17_finalize.py
- `stats(rs)` — 

## research\v17_monthly_audit.py

## research\v17_robustness.py
- `bars_of(code)` — 
- `adx14(bs, i)` — 
- `stage_and_deep(bs, i)` — 
- `is_strong(title)` — 
- `run(non_deep, deep_hold)` — 

## research\v18_contract_audit.py

## research\v18_finalize.py
- `stats(rs)` — 

## research\v20_finalize.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_detailed(bs, i)` — 
- `stats(rs)` — 

## research\v20c_2023.py

## research\v20c_audit.py

## research\v20c_bootstrap.py
- `full_stats()` — 

## research\v20c_contract_audit.py

## research\v20c_density.py

## research\v20c_excess.py
- `bars(path)` — 

## research\v20c_finalize.py
- `bars(path)` — 
- `is_swing_low(bs, j)` — 
- `stage_detailed(bs, i)` — 
- `stats(rs)` — 

## research\v20c_monthly_consist.py

## research\v20c_regime.py
- `report(label, rs)` — 

## research\v20c_riskmetrics.py

## research\v20c_streak.py

## research\v8_finalize.py
- `stats(rs)` — 

## research\v8_monthly_loss.py

## research\v8_oracle.py
- `bars_of(code)` — 
- `stage_base(bs, i, win, acc, mark, dist)` — 
- `stage_oracle(bs, i)` — Independent: 40-bar window, different logic (midpoint + volume slope).

## research\v8_robustness.py
- `bars_of(code)` — 
- `make_stage(win, acc_th, mark_th, dist_th, vt_acc, vt_mark)` — 
- `is_strong(title)` — 
- `build_events(stage_at, ev_stages)` — 
- `r20_of(symbol, entry_date)` — 
- `build_smc(stage_at, smc_stages)` — 
- `combo(ev, smc)` — 
- `stage_at(bs, i)` — 

## research\weight_sensitivity.py
- `yearly(pool)` — 
