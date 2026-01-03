-- MySQL dump 10.13  Distrib 8.0.43, for Win64 (x86_64)
--
-- Host: localhost    Database: word_chain_game_db
-- ------------------------------------------------------
-- Server version	8.0.43

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Current Database: `word_chain_game_db`
--

CREATE DATABASE /*!32312 IF NOT EXISTS*/ `word_chain_game_db` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci */ /*!80016 DEFAULT ENCRYPTION='N' */;

USE `word_chain_game_db`;

--
-- Table structure for table `app_logs`
--

DROP TABLE IF EXISTS `app_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `app_logs` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '고유번호(1부터 자동증가)',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '일시',
  `log_level` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '위험순위',
  `source_class` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '문제 발생 위치',
  `message` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '메세지',
  `stack_trace` text COLLATE utf8mb4_unicode_ci COMMENT '오류 메세지',
  PRIMARY KEY (`id`),
  KEY `idx_created_at` (`created_at`),
  KEY `idx_log_level` (`log_level`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `app_logs`
--

LOCK TABLES `app_logs` WRITE;
/*!40000 ALTER TABLE `app_logs` DISABLE KEYS */;
/*!40000 ALTER TABLE `app_logs` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `game_history`
--

DROP TABLE IF EXISTS `game_history`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `game_history` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '고유번호(1부터 자동증가)',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP COMMENT '일시',
  `nickname` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '닉네임',
  `input_word` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '입력단어',
  `previous_word` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '현재 단어',
  `result_status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '성공/실패',
  `fail_reason` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '실패 이유',
  PRIMARY KEY (`id`),
  KEY `idx_nickname` (`nickname`),
  KEY `idx_word` (`input_word`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping data for table `game_history`
--

LOCK TABLES `game_history` WRITE;
/*!40000 ALTER TABLE `game_history` DISABLE KEYS */;
/*!40000 ALTER TABLE `game_history` ENABLE KEYS */;
UNLOCK TABLES;

--
-- Table structure for table `ko_word`
--

DROP TABLE IF EXISTS `ko_word`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `ko_word` (
  `num` int NOT NULL AUTO_INCREMENT COMMENT '고유번호(1부터 자동증가)',
  `word` varchar(300) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '단어',
  `is_use` tinyint(1) DEFAULT '0' COMMENT '사용 여부',
  `is_use_date` datetime DEFAULT NULL COMMENT '사용된 날짜',
  `is_use_user` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '사용한 유저',
  `can_use` tinyint(1) DEFAULT '1' COMMENT '게임 사용됨/사용 안됨 여부',
  `start_char` char(1) COLLATE utf8mb4_unicode_ci GENERATED ALWAYS AS (left(`word`,1)) STORED,
  `end_char` char(1) COLLATE utf8mb4_unicode_ci GENERATED ALWAYS AS (right(`word`,1)) STORED,
  `source` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '출처',
  `available` tinyint(1) DEFAULT '1' COMMENT '게임 사용 가능 여부',
  PRIMARY KEY (`num`),
  UNIQUE KEY `word` (`word`)
) ENGINE=InnoDB AUTO_INCREMENT=1270538 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

