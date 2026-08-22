package com.arena.voice.ui

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Brain
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.Image
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.NavGraph.Companion.findStartDestination
import com.arena.voice.ui.screens.BeanieScreen
import com.arena.voice.ui.screens.ChatScreen
import com.arena.voice.ui.screens.FilesScreen
import com.arena.voice.ui.screens.PansophyScreen
import com.arena.voice.ui.screens.PresenceStatus
import com.arena.voice.ui.screens.SettingsScreen
import com.arena.voice.ui.screens.VisionScreen

enum class AppTab(val route: String, val label: String, val icon: ImageVector) {
    BEANIE("beanie", "Beanie", Icons.Default.Person),
    CHAT("chat", "Chat", Icons.Default.Chat),
    PANSOPHY("pansophy", "Pansophy", Icons.Default.Brain),
    FILES("files", "Files", Icons.Default.Folder),
    IMAGES("images", "Images", Icons.Default.Image),
    SETTINGS("settings", "Settings", Icons.Default.Settings),
}

/**
 * Root scaffold with bottom navigation, mirroring the web/desktop nav
 * (Beanie / Chat / Pansophy / Files / Settings), optimised for mobile.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AppScaffold(
    presenceStatus: PresenceStatus,
    statusMessage: String,
    isListening: Boolean,
    serverUrl: String,
    apiKey: String,
    onToggleTalk: () -> Unit,
    onQuickAction: (String) -> Unit,
    onSaveServerUrl: (String) -> Unit,
    onSaveApiKey: (String) -> Unit,
    onSaveTheme: (String) -> Unit,
) {
    val navController = rememberNavController()

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        bottomBar = {
            NavigationBar {
                val currentRoute = navController.currentBackStackEntry?.destination?.route
                AppTab.entries.forEach { tab ->
                    NavigationBarItem(
                        selected = currentRoute == tab.route,
                        onClick = {
                            navController.navigate(tab.route) {
                                popUpTo(navController.graph.findStartDestination().id) {
                                    saveState = true
                                }
                                launchSingleTop = true
                                restoreState = true
                            }
                        },
                        icon = { Icon(tab.icon, contentDescription = tab.label) },
                        label = { Text(tab.label) },
                    )
                }
            }
        },
    ) { padding ->
        NavHost(
            navController = navController,
            startDestination = AppTab.CHAT.route,
            modifier = Modifier.padding(padding),
        ) {
            composable(AppTab.BEANIE.route) {
                BeanieScreen(
                    presenceStatus = presenceStatus,
                    statusMessage = statusMessage,
                    isListening = isListening,
                    onToggleTalk = onToggleTalk,
                    onQuickAction = onQuickAction,
                )
            }
            composable(AppTab.CHAT.route) {
                ChatScreen(
                    onVoiceToggle = onToggleTalk,
                    onOpenSettings = {
                        navController.navigate(AppTab.SETTINGS.route) {
                            popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                            launchSingleTop = true
                            restoreState = true
                        }
                    },
                    voiceStatus = presenceStatus,
                )
            }
            composable(AppTab.PANSOPHY.route) {
                PansophyScreen()
            }
            composable(AppTab.FILES.route) {
                FilesScreen()
            }
            composable(AppTab.IMAGES.route) {
                VisionScreen()
            }
            composable(AppTab.SETTINGS.route) {
                SettingsScreen(
                    serverUrl = serverUrl,
                    apiKey = apiKey,
                    onSaveServerUrl = onSaveServerUrl,
                    onSaveApiKey = onSaveApiKey,
                    onSaveTheme = onSaveTheme,
                )
            }
        }
    }
}
