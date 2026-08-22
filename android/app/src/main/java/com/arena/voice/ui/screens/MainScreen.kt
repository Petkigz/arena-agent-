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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowUpward
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.MicOff
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Settings
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
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.math.cos
import kotlin.math.sin

private data class ChatMessage(
    val id: Long,
    val role: Role,
    val text: String
)

private enum class Role { USER, BEANIE }

/** Beanie's compact presence used beside assistant messages and in the header. */
@Composable
private fun BeanieOrb(
    isListening: Boolean,
    isThinking: Boolean = false,
    modifier: Modifier = Modifier,
    size: Float = 44f
) {
    val transition = rememberInfiniteTransition(label = "beanie-orb")
    val pulse by transition.animateFloat(
        initialValue = 0.94f,
        targetValue = when {
            isListening -> 1.12f
            isThinking -> 1.06f
            else -> 1.02f
        },
        animationSpec = infiniteRepeatable(
            tween(if (isListening) 520 else if (isThinking) 900 else 2200, easing = FastOutSlowInEasing),
            RepeatMode.Reverse
        ),
        label = "pulse"
    )
    val rotation by transition.animateFloat(
        initialValue = 0f,
        targetValue = 360f,
        animationSpec = infiniteRepeatable(
            tween(if (isListening || isThinking) 6000 else 16000),
            RepeatMode.Restart
        ),
        label = "rotation"
    )

    Canvas(modifier = modifier.size(size.dp)) {
        val cx = size.width / 2f
        val cy = size.height / 2f
        val core = size.minDimension * 0.28f
        val active = isListening || isThinking
        val lineCount = if (active) 18 else 12

        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(Color(0x554FA3FF), Color(0x222563EB), Color.Transparent),
                center = Offset(cx, cy),
                radius = size.minDimension * 0.48f
            ),
            radius = size.minDimension * 0.48f,
            center = Offset(cx, cy)
        )

        for (i in 0 until lineCount) {
            val angle = Math.toRadians((360.0 / lineCount * i + rotation).toDouble())
            val modulation = if (active) 0.78f + (i % 5) * 0.08f else 0.82f + (i % 3) * 0.05f
            val inner = core * 1.38f
            val outer = inner + core * (if (active) 1.0f else 0.62f) * modulation
            val start = Offset(cx + cos(angle).toFloat() * inner, cy + sin(angle).toFloat() * inner)
            val end = Offset(cx + cos(angle).toFloat() * outer, cy + sin(angle).toFloat() * outer)
            drawLine(
                color = if (isListening) Color(0xFF60A5FA) else Color(0xFF818CF8),
                start = start,
                end = end,
                strokeWidth = if (active) 2.2f else 1.4f,
                cap = StrokeCap.Round,
                alpha = if (active) 0.72f else 0.32f
            )
        }

        drawCircle(
            color = Color(0x444FA3FF),
            radius = core * (1.42f + if (active) pulse * 0.08f else 0f),
            center = Offset(cx, cy),
            style = androidx.compose.ui.graphics.drawscope.Stroke(width = 1.5f)
        )

        drawCircle(
            brush = Brush.radialGradient(
                colors = listOf(Color(0xFFF8FBFF), Color(0xFF60A5FA), Color(0xFF2563EB), Color(0xFF0F172A)),
                center = Offset(cx - core * 0.28f, cy - core * 0.32f),
                radius = core * 1.25f
            ),
            radius = core * pulse,
            center = Offset(cx, cy)
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreen(
    onStartListening: () -> Unit,
    onStopListening: () -> Unit,
    onConnect: () -> Unit,
    onDisconnect: () -> Unit,
    onSendMessage: (String) -> Unit = {}
) {
    var isListening by remember { mutableStateOf(false) }
    var isConnected by remember { mutableStateOf(false) }
    var input by remember { mutableStateOf("") }
    var isThinking by remember { mutableStateOf(false) }
    var conversationTitle by remember { mutableStateOf("New conversation") }
    var drawerState by remember { mutableStateOf(DrawerValue.Closed) }
    val messages = remember {
        mutableStateListOf(
            ChatMessage(1L, Role.BEANIE, "Hi, I'm Beanie. How can I help you today?")
        )
    }
    val listState = rememberLazyListState()
    val scope = rememberCoroutineScope()
    val drawer = rememberDrawerState(initialValue = DrawerValue.Closed)

    LaunchedEffect(drawerState) {
        if (drawerState == DrawerValue.Open) drawer.open() else drawer.close()
    }

    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) listState.animateScrollToItem(messages.lastIndex)
    }

    LaunchedEffect(isThinking) {
        if (isThinking) {
            delay(1200)
            isThinking = false
        }
    }

    fun send() {
        val text = input.trim()
        if (text.isEmpty()) return
        messages += ChatMessage(System.currentTimeMillis(), Role.USER, text)
        input = ""
        conversationTitle = text.take(34)
        isThinking = true
        onSendMessage(text)
        scope.launch { listState.animateScrollToItem(messages.lastIndex) }
    }

    ModalNavigationDrawer(
        drawerState = drawer,
        drawerContent = {
            ModalDrawerSheet(
                drawerContainerColor = Color(0xFF111827),
                drawerContentColor = Color(0xFFF8FAFC),
                modifier = Modifier.width(300.dp)
            ) {
                Spacer(Modifier.height(18.dp))
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    BeanieOrb(isListening = isListening, isThinking = isThinking, size = 38f)
                    Spacer(Modifier.width(10.dp))
                    Column(Modifier.weight(1f)) {
                        Text("Beanie", fontWeight = FontWeight.SemiBold, fontSize = 17.sp)
                        Text("Personal AI", color = Color(0xFF94A3B8), fontSize = 12.sp)
                    }
                    IconButton(onClick = { drawerState = DrawerValue.Closed }) {
                        Icon(Icons.Default.MoreVert, contentDescription = "More", tint = Color(0xFFCBD5E1))
                    }
                }
                Spacer(Modifier.height(18.dp))
                Button(
                    onClick = {
                        messages.clear()
                        messages += ChatMessage(System.currentTimeMillis(), Role.BEANIE, "Hi, I'm Beanie. What are we working on?")
                        conversationTitle = "New conversation"
                        drawerState = DrawerValue.Closed
                    },
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp),
                    shape = RoundedCornerShape(10.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF2563EB))
                ) {
                    Icon(Icons.Default.Add, contentDescription = null)
                    Spacer(Modifier.width(8.dp))
                    Text("New conversation")
                }
                Spacer(Modifier.height(18.dp))
                Text("Chats", color = Color(0xFF64748B), fontSize = 11.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(horizontal = 18.dp))
                NavigationDrawerItem(
                    label = { Text(conversationTitle, maxLines = 1) },
                    selected = true,
                    onClick = { drawerState = DrawerValue.Closed },
                    modifier = Modifier.padding(horizontal = 10.dp, vertical = 3.dp),
                    colors = NavigationDrawerItemDefaults.colors(
                        selectedContainerColor = Color(0xFF1F2937),
                        selectedTextColor = Color(0xFFF8FAFC),
                        unselectedTextColor = Color(0xFFCBD5E1)
                    )
                )
                Spacer(Modifier.weight(1f))
                NavigationDrawerItem(
                    label = { Text("Settings") },
                    selected = false,
                    onClick = { drawerState = DrawerValue.Closed },
                    icon = { Icon(Icons.Default.Settings, contentDescription = null) },
                    modifier = Modifier.padding(10.dp)
                )
                Spacer(Modifier.height(10.dp))
            }
        }
    ) {
        Scaffold(
            containerColor = Color(0xFF0B1020),
            topBar = {
                TopAppBar(
                    title = {
                        Column {
                            Text("Beanie", fontWeight = FontWeight.SemiBold, fontSize = 16.sp)
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Box(Modifier.size(6.dp).clip(CircleShape).background(if (isConnected) Color(0xFF10B981) else Color(0xFF64748B)))
                                Spacer(Modifier.width(5.dp))
                                Text(if (isConnected) "Online" else "Offline", fontSize = 11.sp, color = Color(0xFF94A3B8))
                            }
                        }
                    },
                    navigationIcon = {
                        IconButton(onClick = { drawerState = DrawerValue.Open }) {
                            Icon(Icons.Default.Menu, contentDescription = "Open chats", tint = Color(0xFFCBD5E1))
                        }
                    },
                    actions = {
                        IconButton(onClick = { /* future settings */ }) {
                            Icon(Icons.Default.MoreVert, contentDescription = "More", tint = Color(0xFFCBD5E1))
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(containerColor = Color(0xFF0B1020))
                )
            }
        ) { padding ->
            Column(Modifier.fillMaxSize().padding(padding)) {
                LazyColumn(
                    state = listState,
                    modifier = Modifier.weight(1f).fillMaxWidth(),
                    contentPadding = PaddingValues(horizontal = 16.dp, vertical = 18.dp),
                    verticalArrangement = Arrangement.spacedBy(22.dp)
                ) {
                    items(messages, key = { it.id }) { message ->
                        if (message.role == Role.USER) {
                            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                                Surface(
                                    color = Color(0xFF2563EB),
                                    shape = RoundedCornerShape(18.dp, 18.dp, 4.dp, 18.dp),
                                    modifier = Modifier.widthIn(max = 320.dp)
                                ) {
                                    Text(message.text, modifier = Modifier.padding(horizontal = 15.dp, vertical = 11.dp), color = Color.White, fontSize = 15.sp, lineHeight = 21.sp)
                                }
                            }
                        } else {
                            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
                                BeanieOrb(isListening = isListening, isThinking = isThinking, size = 34f, modifier = Modifier.padding(top = 2.dp))
                                Spacer(Modifier.width(10.dp))
                                Column(Modifier.weight(1f)) {
                                    Text("Beanie", color = Color(0xFFF8FAFC), fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                                    Spacer(Modifier.height(4.dp))
                                    Text(message.text, color = Color(0xFFE2E8F0), fontSize = 15.sp, lineHeight = 22.sp)
                                }
                            }
                        }
                    }
                    if (isThinking) {
                        item {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                BeanieOrb(isListening = false, isThinking = true, size = 34f)
                                Spacer(Modifier.width(10.dp))
                                Text("Beanie is thinking…", color = Color(0xFF94A3B8), fontSize = 13.sp)
                            }
                        }
                    }
                }

                if (!isConnected) {
                    Surface(color = Color(0xFF111827), modifier = Modifier.fillMaxWidth()) {
                        Row(Modifier.padding(horizontal = 16.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.WifiOff, contentDescription = null, tint = Color(0xFF94A3B8), modifier = Modifier.size(16.dp))
                            Spacer(Modifier.width(8.dp))
                            Text("Connect to your PC to send messages", color = Color(0xFF94A3B8), fontSize = 12.sp, modifier = Modifier.weight(1f))
                            TextButton(onClick = { onConnect(); isConnected = true }) { Text("Connect") }
                        }
                    }
                }

                Surface(color = Color(0xFF0B1020), modifier = Modifier.fillMaxWidth()) {
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 10.dp),
                        verticalAlignment = Alignment.Bottom
                    ) {
                        IconButton(onClick = { /* attachments */ }) {
                            Icon(Icons.Default.Add, contentDescription = "Attach", tint = Color(0xFF94A3B8))
                        }
                        TextField(
                            value = input,
                            onValueChange = { input = it },
                            modifier = Modifier.weight(1f),
                            placeholder = { Text("Message Beanie…", color = Color(0xFF64748B)) },
                            maxLines = 5,
                            shape = RoundedCornerShape(22.dp),
                            colors = TextFieldDefaults.colors(
                                focusedContainerColor = Color(0xFF111827),
                                unfocusedContainerColor = Color(0xFF111827),
                                focusedIndicatorColor = Color.Transparent,
                                unfocusedIndicatorColor = Color.Transparent,
                                cursorColor = Color(0xFF60A5FA),
                                focusedTextColor = Color(0xFFF8FAFC),
                                unfocusedTextColor = Color(0xFFF8FAFC)
                            )
                        )
                        Spacer(Modifier.width(6.dp))
                        IconButton(
                            onClick = {
                                if (isListening) {
                                    onStopListening()
                                    isListening = false
                                } else {
                                    onStartListening()
                                    isListening = true
                                }
                            },
                            modifier = Modifier.size(44.dp).clip(CircleShape).background(if (isListening) Color(0xFF2563EB) else Color(0xFF1F2937))
                        ) {
                            Icon(if (isListening) Icons.Default.MicOff else Icons.Default.Mic, contentDescription = if (isListening) "Stop voice" else "Voice input", tint = Color.White)
                        }
                        Spacer(Modifier.width(6.dp))
                        IconButton(
                            onClick = { send() },
                            enabled = input.isNotBlank(),
                            modifier = Modifier.size(44.dp).clip(CircleShape).background(if (input.isNotBlank()) Color(0xFF2563EB) else Color(0xFF1F2937))
                        ) {
                            Icon(Icons.Default.ArrowUpward, contentDescription = "Send", tint = if (input.isNotBlank()) Color.White else Color(0xFF64748B))
                        }
                    }
                }
            }
        }
    }
}
