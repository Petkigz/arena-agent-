package com.arena.voice.ui.screens

import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MicOff
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Wifi
import androidx.compose.material.icons.filled.WifiOff
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.cos
import kotlin.math.sin

@Composable
private fun BeanieOrb(isListening: Boolean, isConnected: Boolean) {
    val transition = rememberInfiniteTransition(label = "beanie-orb")
    val pulse by transition.animateFloat(
        initialValue = 0.94f,
        targetValue = if (isListening) 1.08f else 1.02f,
        animationSpec = infiniteRepeatable(tween(if (isListening) 650 else 2200, easing = FastOutSlowInEasing), RepeatMode.Reverse),
        label = "pulse"
    )
    val rotation by transition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(tween(if (isListening) 7000 else 16000), RepeatMode.Restart),
        label = "rotation"
    )

    Box(
        modifier = Modifier.size(300.dp),
        contentAlignment = Alignment.Center
    ) {
        Canvas(modifier = Modifier.fillMaxSize()) {
            val cx = size.width / 2f
            val cy = size.height / 2f
            val baseRadius = size.minDimension * 0.24f
            val activity = if (isListening) pulse else 1f

            drawCircle(
                brush = Brush.radialGradient(
                    colors = listOf(Color(0x664FA3FF), Color(0x222563EB), Color.Transparent),
                    center = Offset(cx, cy),
                    radius = size.minDimension * 0.48f
                ),
                radius = size.minDimension * 0.48f,
                center = Offset(cx, cy)
            )

            val lineCount = 18
            for (i in 0 until lineCount) {
                val angle = Math.toRadians((360.0 / lineCount * i + rotation).toDouble())
                val wave = if (isListening) (0.75f + ((i % 5) * 0.07f)) * activity else 0.82f + ((i % 4) * 0.04f)
                val inner = baseRadius * 1.35f
                val outer = inner + baseRadius * 0.45f * wave
                val start = Offset(cx + cos(angle).toFloat() * inner, cy + sin(angle).toFloat() * inner)
                val end = Offset(cx + cos(angle).toFloat() * outer, cy + sin(angle).toFloat() * outer)
                drawLine(
                    color = Color(0x9960A5FA),
                    start = start,
                    end = end,
                    strokeWidth = if (isListening) 4f else 2.5f,
                    cap = StrokeCap.Round,
                    alpha = if (isListening) 0.75f else 0.3f
                )
            }

            drawCircle(
                color = Color(0x334F9CFF),
                radius = baseRadius * (1.42f + if (isListening) pulse * 0.08f else 0f),
                center = Offset(cx, cy),
                style = androidx.compose.ui.graphics.drawscope.Stroke(width = 2.5f)
            )

            drawCircle(
                brush = Brush.radialGradient(
                    colors = listOf(Color(0xFFE8F3FF), Color(0xFF60A5FA), Color(0xFF1D4ED8), Color(0xFF0F172A)),
                    center = Offset(cx - baseRadius * 0.28f, cy - baseRadius * 0.32f),
                    radius = baseRadius * 1.25f
                ),
                radius = baseRadius * pulse,
                center = Offset(cx, cy)
            )

            drawCircle(
                color = Color.White.copy(alpha = if (isConnected) 0.9f else 0.35f),
                radius = baseRadius * 0.08f,
                center = Offset(cx - baseRadius * 0.25f, cy - baseRadius * 0.27f)
            )
        }

        IconButton(
            onClick = { /* parent handles listening through the outer button */ },
            modifier = Modifier.size(92.dp)
        ) {
            Icon(
                imageVector = if (isListening) Icons.Default.Mic else Icons.Default.MicOff,
                contentDescription = null,
                tint = Color.White.copy(alpha = 0.92f),
                modifier = Modifier.size(44.dp)
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(
    onStartListening: () -> Unit,
    onStopListening: () -> Unit,
    onConnect: () -> Unit,
    onDisconnect: () -> Unit
) {
    var isListening by remember { mutableStateOf(false) }
    var isConnected by remember { mutableStateOf(false) }
    var currentStatus by remember { mutableStateOf("Ready") }

    Scaffold(
        containerColor = Color(0xFF0B1020),
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("Beanie", fontWeight = FontWeight.SemiBold)
                        Text("Personal AI", fontSize = 11.sp, color = Color(0xFF94A3B8))
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Color(0xFF0B1020)),
                actions = {
                    IconButton(onClick = { /* settings */ }) {
                        Icon(Icons.Default.Settings, contentDescription = "Settings", tint = Color(0xFFCBD5E1))
                    }
                }
            )
        }
    ) { paddingValues ->
        Column(
            modifier = Modifier.fillMaxSize().padding(paddingValues).padding(horizontal = 20.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.SpaceBetween
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(top = 24.dp)) {
                Text(currentStatus, fontSize = 22.sp, fontWeight = FontWeight.Medium, color = Color(0xFFF8FAFC))
                Spacer(Modifier.height(8.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = if (isConnected) Icons.Default.Wifi else Icons.Default.WifiOff,
                        contentDescription = "Connection status",
                        tint = if (isConnected) Color(0xFF10B981) else Color(0xFF64748B),
                        modifier = Modifier.size(18.dp)
                    )
                    Text(if (isConnected) "Connected to PC" else "PC not connected", fontSize = 13.sp, color = Color(0xFF94A3B8))
                }
            }

            Box(contentAlignment = Alignment.Center, modifier = Modifier.fillMaxWidth()) {
                BeanieOrb(isListening = isListening, isConnected = isConnected)
                Button(
                    onClick = {
                        if (isListening) {
                            onStopListening()
                            isListening = false
                            currentStatus = "Ready"
                        } else {
                            onStartListening()
                            isListening = true
                            currentStatus = "Listening..."
                        }
                    },
                    modifier = Modifier.size(92.dp).clip(CircleShape),
                    colors = ButtonDefaults.buttonColors(containerColor = Color.Transparent),
                    contentPadding = PaddingValues(0.dp)
                ) { }
            }

            Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(bottom = 24.dp)) {
                Button(
                    onClick = {
                        if (isConnected) {
                            onDisconnect()
                            isConnected = false
                        } else {
                            onConnect()
                            isConnected = true
                        }
                    },
                    modifier = Modifier.fillMaxWidth(0.86f),
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF2563EB))
                ) { Text(if (isConnected) "Disconnect from PC" else "Connect to PC") }
                Spacer(Modifier.height(10.dp))
                Text(
                    text = if (isListening) "Listening locally" else "Tap the orb to talk",
                    fontSize = 13.sp,
                    color = Color(0xFF94A3B8)
                )
            }
        }
    }
}
