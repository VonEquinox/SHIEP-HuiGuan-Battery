-- MySQL dump 10.13  Distrib 8.0.33, for Win64 (x86_64)
--
-- Host: localhost    Database: battery_soh_db
-- ------------------------------------------------------
-- Server version	8.0.33

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Temporary view structure for view `v_model_performance_overview`
--

DROP TABLE IF EXISTS `v_model_performance_overview`;
/*!50001 DROP VIEW IF EXISTS `v_model_performance_overview`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_model_performance_overview` AS SELECT 
 1 AS `model_id`,
 1 AS `model_name`,
 1 AS `algorithm_type`,
 1 AS `framework`,
 1 AS `user_id`,
 1 AS `created_by`,
 1 AS `model_status`,
 1 AS `trained_at`,
 1 AS `is_active`,
 1 AS `total_training_sessions`,
 1 AS `total_predictions_made`,
 1 AS `avg_initial_loss`,
 1 AS `avg_final_loss`,
 1 AS `avg_best_val_loss`,
 1 AS `avg_training_duration`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `v_battery_data_stats`
--

DROP TABLE IF EXISTS `v_battery_data_stats`;
/*!50001 DROP VIEW IF EXISTS `v_battery_data_stats`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_battery_data_stats` AS SELECT 
 1 AS `battery_id`,
 1 AS `battery_name`,
 1 AS `dataset_type`,
 1 AS `total_readings`,
 1 AS `avg_voltage`,
 1 AS `min_voltage`,
 1 AS `max_voltage`,
 1 AS `avg_temperature`,
 1 AS `min_temperature`,
 1 AS `max_temperature`,
 1 AS `avg_capacity`,
 1 AS `min_capacity`,
 1 AS `max_capacity`,
 1 AS `avg_soh`,
 1 AS `min_soh`,
 1 AS `max_soh`,
 1 AS `avg_soc`,
 1 AS `min_soc`,
 1 AS `max_soc`,
 1 AS `avg_resistance`,
 1 AS `min_cycle_count`,
 1 AS `max_cycle_count`,
 1 AS `avg_rul`,
 1 AS `avg_pcl`,
 1 AS `last_reading_time`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `v_battery_overview`
--

DROP TABLE IF EXISTS `v_battery_overview`;
/*!50001 DROP VIEW IF EXISTS `v_battery_overview`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_battery_overview` AS SELECT 
 1 AS `battery_id`,
 1 AS `battery_name`,
 1 AS `dataset_type`,
 1 AS `status`,
 1 AS `total_cycles`,
 1 AS `soh_mean`,
 1 AS `soh_min`,
 1 AS `soh_max`,
 1 AS `rul_mean`,
 1 AS `pcl_mean`,
 1 AS `data_completeness`,
 1 AS `last_updated`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `v_user_activity_overview`
--

DROP TABLE IF EXISTS `v_user_activity_overview`;
/*!50001 DROP VIEW IF EXISTS `v_user_activity_overview`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_user_activity_overview` AS SELECT 
 1 AS `user_id`,
 1 AS `username`,
 1 AS `email`,
 1 AS `user_status`,
 1 AS `user_created_at`,
 1 AS `total_models`,
 1 AS `total_training_records`,
 1 AS `total_predictions`,
 1 AS `total_datasets`,
 1 AS `total_model_comparisons`,
 1 AS `last_activity`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `v_training_detailed`
--

DROP TABLE IF EXISTS `v_training_detailed`;
/*!50001 DROP VIEW IF EXISTS `v_training_detailed`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_training_detailed` AS SELECT 
 1 AS `training_id`,
 1 AS `user_id`,
 1 AS `trainer`,
 1 AS `model_id`,
 1 AS `model_name`,
 1 AS `algorithm_type`,
 1 AS `dataset_path`,
 1 AS `start_time`,
 1 AS `end_time`,
 1 AS `duration`,
 1 AS `initial_loss`,
 1 AS `final_loss`,
 1 AS `best_val_loss`,
 1 AS `convergence_epoch`,
 1 AS `parameters_count`,
 1 AS `memory_usage`,
 1 AS `gpu_usage`,
 1 AS `cpu_usage`,
 1 AS `status`,
 1 AS `created_at`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `v_dataset_usage`
--

DROP TABLE IF EXISTS `v_dataset_usage`;
/*!50001 DROP VIEW IF EXISTS `v_dataset_usage`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_dataset_usage` AS SELECT 
 1 AS `dataset_id`,
 1 AS `dataset_name`,
 1 AS `description`,
 1 AS `user_id`,
 1 AS `owner`,
 1 AS `file_path`,
 1 AS `file_size`,
 1 AS `num_samples`,
 1 AS `data_format`,
 1 AS `is_active`,
 1 AS `created_at`,
 1 AS `used_in_training_sessions`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `v_prediction_detailed`
--

DROP TABLE IF EXISTS `v_prediction_detailed`;
/*!50001 DROP VIEW IF EXISTS `v_prediction_detailed`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_prediction_detailed` AS SELECT 
 1 AS `prediction_id`,
 1 AS `user_id`,
 1 AS `predictor`,
 1 AS `model_id`,
 1 AS `model_name`,
 1 AS `algorithm_type`,
 1 AS `battery_id`,
 1 AS `battery_name`,
 1 AS `predicted_soh`,
 1 AS `actual_soh`,
 1 AS `predicted_rul`,
 1 AS `actual_rul`,
 1 AS `predicted_pcl`,
 1 AS `actual_pcl`,
 1 AS `confidence`,
 1 AS `prediction_type`,
 1 AS `execution_time`,
 1 AS `prediction_time`,
 1 AS `soh_error`,
 1 AS `rul_error`,
 1 AS `pcl_error`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `v_system_stats`
--

DROP TABLE IF EXISTS `v_system_stats`;
/*!50001 DROP VIEW IF EXISTS `v_system_stats`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_system_stats` AS SELECT 
 1 AS `total_users`,
 1 AS `total_battery_data_points`,
 1 AS `total_batteries`,
 1 AS `total_models`,
 1 AS `total_training_records`,
 1 AS `total_predictions`,
 1 AS `total_datasets`,
 1 AS `total_model_comparisons`,
 1 AS `active_users`,
 1 AS `active_models`,
 1 AS `active_datasets`,
 1 AS `avg_training_duration`,
 1 AS `soh_predictions`,
 1 AS `rul_predictions`,
 1 AS `pcl_predictions`*/;
SET character_set_client = @saved_cs_client;

--
-- Final view structure for view `v_model_performance_overview`
--

/*!50001 DROP VIEW IF EXISTS `v_model_performance_overview`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `v_model_performance_overview` AS select `m`.`id` AS `model_id`,`m`.`name` AS `model_name`,`m`.`algorithm_type` AS `algorithm_type`,`m`.`framework` AS `framework`,`m`.`user_id` AS `user_id`,`u`.`username` AS `created_by`,`m`.`status` AS `model_status`,`m`.`trained_at` AS `trained_at`,`m`.`is_active` AS `is_active`,count(`tr`.`id`) AS `total_training_sessions`,count(`pr`.`id`) AS `total_predictions_made`,avg(`tr`.`initial_loss`) AS `avg_initial_loss`,avg(`tr`.`final_loss`) AS `avg_final_loss`,avg(`tr`.`best_val_loss`) AS `avg_best_val_loss`,avg(`tr`.`duration`) AS `avg_training_duration` from (((`models` `m` left join `users` `u` on((`m`.`user_id` = `u`.`id`))) left join `training_records` `tr` on((`m`.`id` = `tr`.`model_id`))) left join `prediction_records` `pr` on((`m`.`id` = `pr`.`model_id`))) group by `m`.`id`,`m`.`name`,`m`.`algorithm_type`,`m`.`framework`,`m`.`user_id`,`u`.`username`,`m`.`status`,`m`.`trained_at`,`m`.`is_active` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `v_battery_data_stats`
--

/*!50001 DROP VIEW IF EXISTS `v_battery_data_stats`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `v_battery_data_stats` AS select `bld`.`battery_id` AS `battery_id`,`bi`.`battery_name` AS `battery_name`,`bi`.`dataset_type` AS `dataset_type`,count(0) AS `total_readings`,avg(`bld`.`voltage`) AS `avg_voltage`,min(`bld`.`voltage`) AS `min_voltage`,max(`bld`.`voltage`) AS `max_voltage`,avg(`bld`.`temperature`) AS `avg_temperature`,min(`bld`.`temperature`) AS `min_temperature`,max(`bld`.`temperature`) AS `max_temperature`,avg(`bld`.`capacity`) AS `avg_capacity`,min(`bld`.`capacity`) AS `min_capacity`,max(`bld`.`capacity`) AS `max_capacity`,avg(`bld`.`soh`) AS `avg_soh`,min(`bld`.`soh`) AS `min_soh`,max(`bld`.`soh`) AS `max_soh`,avg(`bld`.`soc`) AS `avg_soc`,min(`bld`.`soc`) AS `min_soc`,max(`bld`.`soc`) AS `max_soc`,avg(`bld`.`resistance`) AS `avg_resistance`,min(`bld`.`cycle_count`) AS `min_cycle_count`,max(`bld`.`cycle_count`) AS `max_cycle_count`,avg(`bld`.`rul`) AS `avg_rul`,avg(`bld`.`pcl`) AS `avg_pcl`,max(`bld`.`test_timestamp`) AS `last_reading_time` from (`battery_lifecycle_data` `bld` join `battery_info` `bi` on((`bld`.`battery_id` = `bi`.`battery_id`))) group by `bld`.`battery_id`,`bi`.`battery_name`,`bi`.`dataset_type` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `v_battery_overview`
--

/*!50001 DROP VIEW IF EXISTS `v_battery_overview`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `v_battery_overview` AS select `bi`.`battery_id` AS `battery_id`,`bi`.`battery_name` AS `battery_name`,`bi`.`dataset_type` AS `dataset_type`,`bi`.`status` AS `status`,`bi`.`total_cycles` AS `total_cycles`,`ds`.`soh_mean` AS `soh_mean`,`ds`.`soh_min` AS `soh_min`,`ds`.`soh_max` AS `soh_max`,`ds`.`rul_mean` AS `rul_mean`,`ds`.`pcl_mean` AS `pcl_mean`,`ds`.`data_completeness` AS `data_completeness`,`ds`.`last_updated` AS `last_updated` from (`battery_info` `bi` left join `data_statistics` `ds` on((`bi`.`battery_id` = `ds`.`battery_id`))) */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `v_user_activity_overview`
--

/*!50001 DROP VIEW IF EXISTS `v_user_activity_overview`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `v_user_activity_overview` AS select `u`.`id` AS `user_id`,`u`.`username` AS `username`,`u`.`email` AS `email`,`u`.`status` AS `user_status`,`u`.`created_at` AS `user_created_at`,count(distinct `m`.`id`) AS `total_models`,count(distinct `tr`.`id`) AS `total_training_records`,count(distinct `pr`.`id`) AS `total_predictions`,count(distinct `ds`.`id`) AS `total_datasets`,count(distinct `mc`.`id`) AS `total_model_comparisons`,max(`u`.`updated_at`) AS `last_activity` from (((((`users` `u` left join `models` `m` on((`u`.`id` = `m`.`user_id`))) left join `training_records` `tr` on((`u`.`id` = `tr`.`user_id`))) left join `prediction_records` `pr` on((`u`.`id` = `pr`.`user_id`))) left join `datasets` `ds` on((`u`.`id` = `ds`.`user_id`))) left join `model_comparisons` `mc` on((`u`.`id` = `mc`.`created_by`))) group by `u`.`id`,`u`.`username`,`u`.`email`,`u`.`status`,`u`.`created_at` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `v_training_detailed`
--

/*!50001 DROP VIEW IF EXISTS `v_training_detailed`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `v_training_detailed` AS select `tr`.`id` AS `training_id`,`tr`.`user_id` AS `user_id`,`u`.`username` AS `trainer`,`tr`.`model_id` AS `model_id`,`m`.`name` AS `model_name`,`m`.`algorithm_type` AS `algorithm_type`,`tr`.`dataset_path` AS `dataset_path`,`tr`.`start_time` AS `start_time`,`tr`.`end_time` AS `end_time`,`tr`.`duration` AS `duration`,`tr`.`initial_loss` AS `initial_loss`,`tr`.`final_loss` AS `final_loss`,`tr`.`best_val_loss` AS `best_val_loss`,`tr`.`convergence_epoch` AS `convergence_epoch`,`tr`.`parameters_count` AS `parameters_count`,`tr`.`memory_usage` AS `memory_usage`,`tr`.`gpu_usage` AS `gpu_usage`,`tr`.`cpu_usage` AS `cpu_usage`,`tr`.`status` AS `status`,`tr`.`created_at` AS `created_at` from ((`training_records` `tr` join `users` `u` on((`tr`.`user_id` = `u`.`id`))) join `models` `m` on((`tr`.`model_id` = `m`.`id`))) */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `v_dataset_usage`
--

/*!50001 DROP VIEW IF EXISTS `v_dataset_usage`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `v_dataset_usage` AS select `ds`.`id` AS `dataset_id`,`ds`.`name` AS `dataset_name`,`ds`.`description` AS `description`,`ds`.`user_id` AS `user_id`,`u`.`username` AS `owner`,`ds`.`file_path` AS `file_path`,`ds`.`file_size` AS `file_size`,`ds`.`num_samples` AS `num_samples`,`ds`.`data_format` AS `data_format`,`ds`.`is_active` AS `is_active`,`ds`.`created_at` AS `created_at`,count(distinct `tr`.`id`) AS `used_in_training_sessions` from ((`datasets` `ds` join `users` `u` on((`ds`.`user_id` = `u`.`id`))) left join `training_records` `tr` on((`tr`.`dataset_path` like concat('%',`ds`.`name`,'%')))) group by `ds`.`id`,`ds`.`name`,`ds`.`description`,`ds`.`user_id`,`u`.`username`,`ds`.`file_path`,`ds`.`file_size`,`ds`.`num_samples`,`ds`.`data_format`,`ds`.`is_active`,`ds`.`created_at` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `v_prediction_detailed`
--

/*!50001 DROP VIEW IF EXISTS `v_prediction_detailed`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `v_prediction_detailed` AS select `pr`.`id` AS `prediction_id`,`pr`.`user_id` AS `user_id`,`u`.`username` AS `predictor`,`pr`.`model_id` AS `model_id`,`m`.`name` AS `model_name`,`m`.`algorithm_type` AS `algorithm_type`,`pr`.`battery_id` AS `battery_id`,`bi`.`battery_name` AS `battery_name`,`pr`.`predicted_soh` AS `predicted_soh`,`pr`.`actual_soh` AS `actual_soh`,`pr`.`predicted_rul` AS `predicted_rul`,`pr`.`actual_rul` AS `actual_rul`,`pr`.`predicted_pcl` AS `predicted_pcl`,`pr`.`actual_pcl` AS `actual_pcl`,`pr`.`confidence` AS `confidence`,`pr`.`prediction_type` AS `prediction_type`,`pr`.`execution_time` AS `execution_time`,`pr`.`prediction_time` AS `prediction_time`,abs((coalesce(`pr`.`predicted_soh`,0) - coalesce(`pr`.`actual_soh`,0))) AS `soh_error`,abs((coalesce(`pr`.`predicted_rul`,0) - coalesce(`pr`.`actual_rul`,0))) AS `rul_error`,abs((coalesce(`pr`.`predicted_pcl`,0) - coalesce(`pr`.`actual_pcl`,0))) AS `pcl_error` from (((`prediction_records` `pr` join `users` `u` on((`pr`.`user_id` = `u`.`id`))) join `models` `m` on((`pr`.`model_id` = `m`.`id`))) join `battery_info` `bi` on((`pr`.`battery_id` = `bi`.`battery_id`))) */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `v_system_stats`
--

/*!50001 DROP VIEW IF EXISTS `v_system_stats`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`root`@`localhost` SQL SECURITY DEFINER */
/*!50001 VIEW `v_system_stats` AS select (select count(0) from `users`) AS `total_users`,(select count(0) from `battery_lifecycle_data`) AS `total_battery_data_points`,(select count(0) from `battery_info`) AS `total_batteries`,(select count(0) from `models`) AS `total_models`,(select count(0) from `training_records`) AS `total_training_records`,(select count(0) from `prediction_records`) AS `total_predictions`,(select count(0) from `datasets`) AS `total_datasets`,(select count(0) from `model_comparisons`) AS `total_model_comparisons`,(select count(0) from `users` where (`users`.`status` = true)) AS `active_users`,(select count(0) from `models` where (`models`.`is_active` = true)) AS `active_models`,(select count(0) from `datasets` where (`datasets`.`is_active` = true)) AS `active_datasets`,(select avg(`training_records`.`duration`) from `training_records` where (`training_records`.`status` = 'completed')) AS `avg_training_duration`,(select count(0) from `prediction_records` where (`prediction_records`.`prediction_type` = 'soh')) AS `soh_predictions`,(select count(0) from `prediction_records` where (`prediction_records`.`prediction_type` = 'rul')) AS `rul_predictions`,(select count(0) from `prediction_records` where (`prediction_records`.`prediction_type` = 'pcl')) AS `pcl_predictions` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Dumping routines for database 'battery_soh_db'
--
/*!50003 DROP PROCEDURE IF EXISTS `check_data_consistency` */;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
CREATE DEFINER=`root`@`localhost` PROCEDURE `check_data_consistency`()
BEGIN
    SELECT COUNT(*) INTO @orphaned_models
    FROM models m
    LEFT JOIN users u ON m.user_id = u.id
    WHERE u.id IS NULL;
    SELECT COUNT(*) INTO @orphaned_training
    FROM training_records tr
    LEFT JOIN users u ON tr.user_id = u.id
    LEFT JOIN models m ON tr.model_id = m.id
    WHERE u.id IS NULL OR m.id IS NULL;
    SELECT COUNT(*) INTO @orphaned_predictions
    FROM prediction_records pr
    LEFT JOIN users u ON pr.user_id = u.id
    LEFT JOIN models m ON pr.model_id = m.id
    LEFT JOIN battery_info bi ON pr.battery_id = bi.battery_id
    WHERE u.id IS NULL OR m.id IS NULL OR bi.battery_id IS NULL;
    SELECT COUNT(*) INTO @orphaned_datasets
    FROM datasets ds
    LEFT JOIN users u ON ds.user_id = u.id
    WHERE u.id IS NULL;
    SELECT COUNT(*) INTO @orphaned_comparisons
    FROM model_comparisons mc
    LEFT JOIN users u ON mc.created_by = u.id
    WHERE u.id IS NULL;
    SELECT 
        'Data Consistency Check' AS check_type,
        @orphaned_models AS orphaned_models,
        @orphaned_training AS orphaned_training,
        @orphaned_predictions AS orphaned_predictions,
        @orphaned_datasets AS orphaned_datasets,
        @orphaned_comparisons AS orphaned_comparisons,
        (@orphaned_models + @orphaned_training + 
         @orphaned_predictions + @orphaned_datasets + @orphaned_comparisons) AS total_inconsistencies;
END ;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 DROP PROCEDURE IF EXISTS `cleanup_old_data` */;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
CREATE DEFINER=`root`@`localhost` PROCEDURE `cleanup_old_data`(IN p_days_old INT)
BEGIN
    DECLARE v_deleted_count INT DEFAULT 0;
    DELETE FROM prediction_records 
    WHERE created_at < DATE_SUB(NOW(), INTERVAL p_days_old DAY);
    SET v_deleted_count = ROW_COUNT();
    DELETE FROM training_records 
    WHERE created_at < DATE_SUB(NOW(), INTERVAL p_days_old DAY);
    SET v_deleted_count = v_deleted_count + ROW_COUNT();
    SELECT CONCAT('总共删除了 ', v_deleted_count, ' 条旧数据记录') AS cleanup_result;
END ;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 DROP PROCEDURE IF EXISTS `get_model_performance_report` */;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
CREATE DEFINER=`root`@`localhost` PROCEDURE `get_model_performance_report`(IN p_model_id INT)
BEGIN
    SELECT 
        m.name AS model_name,
        m.algorithm_type,
        m.framework,
        COUNT(tr.id) AS total_training_sessions,
        AVG(tr.initial_loss) AS avg_initial_loss,
        AVG(tr.final_loss) AS avg_final_loss,
        AVG(tr.best_val_loss) AS avg_best_val_loss,
        AVG(tr.duration) AS avg_training_duration,
        MIN(tr.start_time) AS first_training,
        MAX(tr.end_time) AS latest_training,
        COUNT(pr.id) AS total_predictions
    FROM models m
    LEFT JOIN training_records tr ON m.id = tr.model_id
    LEFT JOIN prediction_records pr ON m.id = pr.model_id
    WHERE m.id = p_model_id OR p_model_id IS NULL
    GROUP BY m.id, m.name, m.algorithm_type, m.framework;
END ;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 DROP PROCEDURE IF EXISTS `get_system_health_report` */;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
CREATE DEFINER=`root`@`localhost` PROCEDURE `get_system_health_report`()
BEGIN
    SELECT 
        'Basic Stats' AS report_section,
        (SELECT COUNT(*) FROM users) AS total_users,
        (SELECT COUNT(*) FROM battery_lifecycle_data) AS total_battery_data,
        (SELECT COUNT(*) FROM models) AS total_models,
        (SELECT COUNT(*) FROM training_records) AS total_training_records,
        (SELECT COUNT(*) FROM prediction_records) AS total_predictions,
        (SELECT COUNT(*) FROM datasets) AS total_datasets,
        (SELECT COUNT(*) FROM battery_info) AS total_batteries;
    SELECT 
        'Active Users' AS report_section,
        COUNT(*) AS active_user_count,
        (SELECT COUNT(*) FROM users WHERE status = TRUE) AS active_status_count
    FROM users WHERE status = TRUE;
    SELECT 
        'Model Status' AS report_section,
        status,
        COUNT(*) AS count
    FROM models
    GROUP BY status;
    SELECT 
        'Recent Activity (Last 7 Days)' AS report_section,
        (SELECT COUNT(*) FROM training_records WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)) AS recent_training,
        (SELECT COUNT(*) FROM prediction_records WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)) AS recent_predictions;
END ;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 DROP PROCEDURE IF EXISTS `update_battery_statistics` */;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
CREATE DEFINER=`root`@`localhost` PROCEDURE `update_battery_statistics`(IN p_battery_id INT)
BEGIN
    INSERT INTO data_statistics (
        battery_id,
        voltage_mean, voltage_min, voltage_max, voltage_std, voltage_variance,
        current_mean, current_min, current_max, current_std, current_variance,
        temperature_mean, temperature_min, temperature_max, temperature_std, temperature_variance,
        capacity_mean, capacity_min, capacity_max, capacity_std, capacity_variance,
        resistance_mean, resistance_min, resistance_max, resistance_std, resistance_variance,
        soc_mean, soc_min, soc_max, soc_std, soc_variance,
        soh_mean, soh_min, soh_max, soh_std, soh_variance,
        power_mean, power_min, power_max, power_std, power_variance,
        rul_mean, rul_min, rul_max, rul_std,
        pcl_mean, pcl_min, pcl_max, pcl_std,
        total_cycles
    )
    SELECT 
        p_battery_id AS battery_id,
        AVG(voltage), MIN(voltage), MAX(voltage), STDDEV(voltage), VARIANCE(voltage),
        AVG(current), MIN(current), MAX(current), STDDEV(current), VARIANCE(current),
        AVG(temperature), MIN(temperature), MAX(temperature), STDDEV(temperature), VARIANCE(temperature),
        AVG(capacity), MIN(capacity), MAX(capacity), STDDEV(capacity), VARIANCE(capacity),
        AVG(resistance), MIN(resistance), MAX(resistance), STDDEV(resistance), VARIANCE(resistance),
        AVG(soc), MIN(soc), MAX(soc), STDDEV(soc), VARIANCE(soc),
        AVG(soh), MIN(soh), MAX(soh), STDDEV(soh), VARIANCE(soh),
        AVG(power), MIN(power), MAX(power), STDDEV(power), VARIANCE(power),
        AVG(rul), MIN(rul), MAX(rul), STDDEV(rul),
        AVG(pcl), MIN(pcl), MAX(pcl), STDDEV(pcl),
        MAX(cycle_count)
    FROM battery_lifecycle_data
    WHERE battery_id = p_battery_id
    ON DUPLICATE KEY UPDATE
        voltage_mean = VALUES(voltage_mean),
        voltage_min = VALUES(voltage_min),
        voltage_max = VALUES(voltage_max),
        voltage_std = VALUES(voltage_std),
        voltage_variance = VALUES(voltage_variance),
        current_mean = VALUES(current_mean),
        current_min = VALUES(current_min),
        current_max = VALUES(current_max),
        current_std = VALUES(current_std),
        current_variance = VALUES(current_variance),
        temperature_mean = VALUES(temperature_mean),
        temperature_min = VALUES(temperature_min),
        temperature_max = VALUES(temperature_max),
        temperature_std = VALUES(temperature_std),
        temperature_variance = VALUES(temperature_variance),
        capacity_mean = VALUES(capacity_mean),
        capacity_min = VALUES(capacity_min),
        capacity_max = VALUES(capacity_max),
        capacity_std = VALUES(capacity_std),
        capacity_variance = VALUES(capacity_variance),
        resistance_mean = VALUES(resistance_mean),
        resistance_min = VALUES(resistance_min),
        resistance_max = VALUES(resistance_max),
        resistance_std = VALUES(resistance_std),
        resistance_variance = VALUES(resistance_variance),
        soc_mean = VALUES(soc_mean),
        soc_min = VALUES(soc_min),
        soc_max = VALUES(soc_max),
        soc_std = VALUES(soc_std),
        soc_variance = VALUES(soc_variance),
        soh_mean = VALUES(soh_mean),
        soh_min = VALUES(soh_min),
        soh_max = VALUES(soh_max),
        soh_std = VALUES(soh_std),
        soh_variance = VALUES(soh_variance),
        power_mean = VALUES(power_mean),
        power_min = VALUES(power_min),
        power_max = VALUES(power_max),
        power_std = VALUES(power_std),
        power_variance = VALUES(power_variance),
        rul_mean = VALUES(rul_mean),
        rul_min = VALUES(rul_min),
        rul_max = VALUES(rul_max),
        rul_std = VALUES(rul_std),
        pcl_mean = VALUES(pcl_mean),
        pcl_min = VALUES(pcl_min),
        pcl_max = VALUES(pcl_max),
        pcl_std = VALUES(pcl_std),
        total_cycles = VALUES(total_cycles);
END ;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!50003 DROP PROCEDURE IF EXISTS `update_user_activity_stats` */;
/*!50003 SET @saved_cs_client      = @@character_set_client */ ;
/*!50003 SET @saved_cs_results     = @@character_set_results */ ;
/*!50003 SET @saved_col_connection = @@collation_connection */ ;
/*!50003 SET character_set_client  = utf8mb4 */ ;
/*!50003 SET character_set_results = utf8mb4 */ ;
/*!50003 SET collation_connection  = utf8mb4_0900_ai_ci */ ;
/*!50003 SET @saved_sql_mode       = @@sql_mode */ ;
/*!50003 SET sql_mode              = 'ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION' */ ;
DELIMITER ;;
CREATE DEFINER=`root`@`localhost` PROCEDURE `update_user_activity_stats`(IN p_user_id INT)
BEGIN
    SELECT 
        u.username,
        COUNT(DISTINCT m.id) AS model_count,
        COUNT(DISTINCT tr.id) AS training_count,
        COUNT(DISTINCT pr.id) AS prediction_count,
        COUNT(DISTINCT ds.id) AS dataset_count
    FROM users u
    LEFT JOIN models m ON u.id = m.user_id
    LEFT JOIN training_records tr ON u.id = tr.user_id
    LEFT JOIN prediction_records pr ON u.id = pr.user_id
    LEFT JOIN datasets ds ON u.id = ds.user_id
    WHERE u.id = p_user_id
    GROUP BY u.id, u.username;
END ;;
DELIMITER ;
/*!50003 SET sql_mode              = @saved_sql_mode */ ;
/*!50003 SET character_set_client  = @saved_cs_client */ ;
/*!50003 SET character_set_results = @saved_cs_results */ ;
/*!50003 SET collation_connection  = @saved_col_connection */ ;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-01-16 12:07:46
