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
-- Table structure for table `model_comparisons`
--

DROP TABLE IF EXISTS `model_comparisons`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `model_comparisons` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT '比较ID',
  `comparison_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '比较名称',
  `compared_models` text COLLATE utf8mb4_unicode_ci COMMENT '参与比较的模型 IDs JSON字符串',
  `comparison_metrics` text COLLATE utf8mb4_unicode_ci COMMENT '比较指标 JSON字符串',
  `comparison_results` text COLLATE utf8mb4_unicode_ci COMMENT '比较结果 JSON字符串',
  `statistical_tests` text COLLATE utf8mb4_unicode_ci COMMENT '统计检验结果 JSON字符串',
  `visualization_data` text COLLATE utf8mb4_unicode_ci COMMENT '可视化数据 JSON字符串',
  `created_by` int NOT NULL COMMENT '创建者ID',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  `is_active` tinyint(1) DEFAULT '1' COMMENT '是否激活',
  PRIMARY KEY (`id`),
  KEY `idx_created_by` (`created_by`),
  KEY `idx_comparison_name` (`comparison_name`),
  KEY `idx_is_active` (`is_active`),
  CONSTRAINT `model_comparisons_ibfk_1` FOREIGN KEY (`created_by`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='模型比较表';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `model_comparisons`
--

LOCK TABLES `model_comparisons` WRITE;
/*!40000 ALTER TABLE `model_comparisons` DISABLE KEYS */;
INSERT INTO `model_comparisons` VALUES (1,'电池寿命预测算法性能分析报告','[72,67]','[\"rmspe\",\"mse\",\"r2\",\"mae\",\"mape\"]','[{\"id\":72,\"algorithm\":\"bilstm\",\"rmspe\":0.0324,\"mse\":0.0008,\"r2\":0.95,\"mae\":0.02,\"mape\":0.015},{\"id\":67,\"algorithm\":\"deepphm\",\"rmspe\":0.0324,\"mse\":0.0008,\"r2\":0.95,\"mae\":0.02,\"mape\":0.015}]',NULL,'{\"performance_chart\":[\"rmspe\",\"mse\",\"r2\"],\"comparison_type\":\"algorithm\"}',4,'2026-01-15 01:52:01','2026-01-15 01:52:01',1),(2,'模型对比_Baseline_vs_BiLSTM_vs_DeepHPM_2026-01-15','[49,46,50]','[\"rmspe\",\"mse\",\"r2\",\"mae\"]','[{\"id\":49,\"algorithm\":\"baseline\",\"algorithmName\":\"BASELINE_20260112_151059\",\"rmspe\":0.0324,\"mse\":0.0008,\"r2\":0.95,\"mae\":0.02,\"trainingTime\":64.8463,\"parameters\":2.4},{\"id\":46,\"algorithm\":\"bilstm\",\"algorithmName\":\"BILSTM_20260112_145111\",\"rmspe\":0.0324,\"mse\":0.0008,\"r2\":0.95,\"mae\":0.02,\"trainingTime\":274.476,\"parameters\":4.2},{\"id\":50,\"algorithm\":\"deepphm\",\"algorithmName\":\"DEEPPHM_20260112_151312\",\"rmspe\":0.0324,\"mse\":0.0008,\"r2\":0.95,\"mae\":0.02,\"trainingTime\":124.703,\"parameters\":6.8}]',NULL,'{\"comparison_type\":\"manual_selection\",\"selected_count\":3}',1,'2026-01-15 03:30:34','2026-01-15 03:30:34',1),(3,'电池寿命预测算法性能分析报告','[49,74,50]','[\"rmspe\",\"mse\",\"r2\",\"mae\",\"mape\"]','[{\"id\":49,\"algorithm\":\"baseline\",\"rmspe\":0.0324,\"mse\":0.0008,\"r2\":0.95,\"mae\":0.02,\"mape\":0.015},{\"id\":74,\"algorithm\":\"bilstm\",\"rmspe\":0.0324,\"mse\":0.0008,\"r2\":0.95,\"mae\":0.02,\"mape\":0.015},{\"id\":50,\"algorithm\":\"deepphm\",\"rmspe\":0.0324,\"mse\":0.0008,\"r2\":0.95,\"mae\":0.02,\"mape\":0.015}]',NULL,'{\"performance_chart\":[\"rmspe\",\"mse\",\"r2\",\"mape\"],\"comparison_type\":\"algorithm\"}',1,'2026-01-15 05:39:23','2026-01-15 05:39:23',1),(4,'模型对比_Baseline_vs_BiLSTM_vs_DeepHPM_2026-01-16','[75,46,50]','[\"rmspe\",\"mse\",\"r2\",\"mae\"]','[{\"id\":75,\"algorithm\":\"baseline\",\"algorithmName\":\"BASELINE_20260116_103718\",\"rmspe\":0.0324,\"mse\":0.0008,\"r2\":0.95,\"mae\":0.02,\"trainingTime\":120.004,\"parameters\":2.4},{\"id\":46,\"algorithm\":\"bilstm\",\"algorithmName\":\"BILSTM_20260112_145111\",\"rmspe\":0.0324,\"mse\":0.0008,\"r2\":0.95,\"mae\":0.02,\"trainingTime\":274.476,\"parameters\":4.2},{\"id\":50,\"algorithm\":\"deepphm\",\"algorithmName\":\"DEEPPHM_20260112_151312\",\"rmspe\":0.0324,\"mse\":0.0008,\"r2\":0.95,\"mae\":0.02,\"trainingTime\":124.703,\"parameters\":6.8}]',NULL,'{\"comparison_type\":\"manual_selection\",\"selected_count\":3}',1,'2026-01-16 02:54:11','2026-01-16 02:54:11',1),(5,'电池寿命预测算法性能分析报告','[76,74,50]','[\"rmspe\",\"mse\",\"r2\",\"mae\",\"mape\"]','[{\"id\":76,\"algorithm\":\"baseline\",\"rmspe\":0.0324,\"mse\":0.0008,\"r2\":0.95,\"mae\":0.02,\"mape\":0.015},{\"id\":74,\"algorithm\":\"bilstm\",\"rmspe\":0.0324,\"mse\":0.0008,\"r2\":0.95,\"mae\":0.02,\"mape\":0.015},{\"id\":50,\"algorithm\":\"deepphm\",\"rmspe\":0.0324,\"mse\":0.0008,\"r2\":0.95,\"mae\":0.02,\"mape\":0.015}]',NULL,'{\"performance_chart\":[\"rmspe\",\"mse\",\"r2\",\"mape\"],\"comparison_type\":\"algorithm\"}',1,'2026-01-16 02:54:25','2026-01-16 02:54:25',1),(6,'模型对比_Baseline_vs_BiLSTM_2026-01-16','[75,46]','[\"rmspe\",\"mse\",\"r2\",\"mae\"]','[{\"id\":75,\"algorithm\":\"baseline\",\"algorithmName\":\"BASELINE_20260116_103718\",\"rmspe\":0.0324,\"mse\":0.0008,\"r2\":0.95,\"mae\":0.02,\"trainingTime\":120.004,\"parameters\":2.4},{\"id\":46,\"algorithm\":\"bilstm\",\"algorithmName\":\"BILSTM_20260112_145111\",\"rmspe\":0.0324,\"mse\":0.0008,\"r2\":0.95,\"mae\":0.02,\"trainingTime\":274.476,\"parameters\":4.2}]',NULL,'{\"comparison_type\":\"manual_selection\",\"selected_count\":2}',1,'2026-01-16 03:15:54','2026-01-16 03:15:54',1),(7,'电池寿命预测算法性能分析报告','[77,46,50]','[\"rmspe\",\"mse\",\"r2\",\"mae\",\"mape\"]','[{\"id\":77,\"algorithm\":\"baseline\",\"rmspe\":0.0324,\"mse\":0.0008,\"r2\":0.95,\"mae\":0.02,\"mape\":0.015},{\"id\":46,\"algorithm\":\"bilstm\",\"rmspe\":0.0324,\"mse\":0.0008,\"r2\":0.95,\"mae\":0.02,\"mape\":0.015},{\"id\":50,\"algorithm\":\"deepphm\",\"rmspe\":0.0324,\"mse\":0.0008,\"r2\":0.95,\"mae\":0.02,\"mape\":0.015}]',NULL,'{\"performance_chart\":[\"rmspe\",\"mse\",\"r2\"],\"comparison_type\":\"metric\"}',1,'2026-01-16 03:16:07','2026-01-16 03:16:07',1);
/*!40000 ALTER TABLE `model_comparisons` ENABLE KEYS */;
UNLOCK TABLES;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-01-16 12:07:45
