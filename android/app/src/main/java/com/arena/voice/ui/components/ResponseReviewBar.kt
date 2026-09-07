package com.arena.voice.ui.components

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.arena.voice.ui.theme.ArenaRadius
import com.arena.voice.ui.theme.Spacing

/**
 * Review response — the Android counterpart of the web/desktop Review bar.
 *
 * Mounted ONLY under a finished assistant reply that carries its exact trace
 * id (the caller gates on `msg.traceId.isNotBlank()`); older unlinked replies
 * are intentionally unreviewable — never guessable. Both actions reuse the
 * SAME backend stores as web/desktop:
 *
 *  - Usefulness feedback feeds the existing bounded strategy-learning path.
 *  - Task evaluations are MEASUREMENT ONLY (stated in the UI): they change no
 *    runtime truth, authorize no work, and approve no training.
 *  - "Why this response?" shows the grounded persisted-trace facts via the
 *    existing introspection endpoint — never a model self-narration.
 */
@Composable
fun ResponseReviewBar(
    traceId: String,
    usefulnessLevels: List<String>,
    taskOutcomes: List<String>,
    onRecordUsefulness: (usefulness: String, note: String, onResult: (Boolean, String) -> Unit) -> Unit,
    onRecordEvaluation: (taskKey: String, observedOutcome: String, correctionReceived: Boolean, note: String, onResult: (Boolean, String) -> Unit) -> Unit,
    onLoadSummary: (onResult: (Pair<Int, Int>?) -> Unit) -> Unit,
    onExplain: (onResult: (List<String>, verified: Boolean) -> Unit) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    var summaryLoaded by remember { mutableStateOf(false) }
    var summary by remember { mutableStateOf<Pair<Int, Int>?>(null) }
    var note by remember { mutableStateOf("") }
    var feedbackStatus by remember { mutableStateOf("") }
    var evalExpanded by remember { mutableStateOf(false) }
    var taskKey by remember { mutableStateOf("") }
    var selectedOutcome by remember { mutableStateOf("") }
    var correctionReceived by remember { mutableStateOf(false) }
    var evalNote by remember { mutableStateOf("") }
    var evalStatus by remember { mutableStateOf("") }
    var explanation by remember { mutableStateOf<List<String>?>(null) }
    var explanationVerified by remember { mutableStateOf(false) }

    fun usefulnessLabel(level: String): String = when (level) {
        "helpful" -> "Helpful"
        "partially_helpful" -> "Partially"
        "not_helpful" -> "Not helpful"
        else -> level
    }

    fun outcomeLabel(outcome: String): String = when (outcome) {
        "success" -> "Success"
        "failure" -> "Failure"
        "unknown" -> "Unknown"
        else -> outcome
    }

    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant,
        shape = RoundedCornerShape(ArenaRadius.lg),
        modifier = Modifier
            .fillMaxWidth()
            .padding(start = 36.dp),
    ) {
        Column(Modifier.padding(Spacing.md)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                TextButton(onClick = {
                    expanded = !expanded
                    if (expanded && !summaryLoaded) {
                        summaryLoaded = true
                        onLoadSummary { result -> summary = result }
                    }
                }) { Text("Review response", fontSize = 12.sp) }
                Spacer(Modifier.width(Spacing.sm))
                TextButton(onClick = {
                    onExplain { lines, verified ->
                        explanation = lines
                        explanationVerified = verified
                    }
                }) { Text("Why this response?", fontSize = 12.sp) }
                summary?.let { (fb, ev) ->
                    if (fb > 0 || ev > 0) {
                        Spacer(Modifier.width(Spacing.sm))
                        Text(
                            "Already recorded: $fb feedback · $ev evaluation(s)",
                            fontSize = 11.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
            feedbackStatus.ifBlank { null }?.let {
                Text(it, fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }

            if (expanded) {
                Spacer(Modifier.height(Spacing.xs))
                Row(verticalAlignment = Alignment.CenterVertically) {
                    usefulnessLevels.forEach { level ->
                        TextButton(onClick = {
                            onRecordUsefulness(level, note) { ok, msg -> feedbackStatus = msg }
                        }) { Text(usefulnessLabel(level), fontSize = 12.sp) }
                    }
                }
                OutlinedTextField(
                    value = note,
                    onValueChange = { note = it },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true,
                    textStyle = MaterialTheme.typography.bodySmall,
                    placeholder = {
                        Text("Note (optional) — what worked or what missed", fontSize = 11.sp)
                    },
                )

                Spacer(Modifier.height(Spacing.xs))
                TextButton(onClick = { evalExpanded = !evalExpanded }) {
                    Text(
                        if (evalExpanded) "Record a task evaluation ▾" else "Record a task evaluation ▸",
                        fontSize = 12.sp,
                    )
                }
                if (evalExpanded) {
                    Text(
                        "Measurement only — recorded against this exact trace. It does " +
                            "not change runtime truth, authorize work, or approve training.",
                        fontSize = 11.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(Modifier.height(Spacing.xs))
                    OutlinedTextField(
                        value = taskKey,
                        onValueChange = { taskKey = it },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        textStyle = MaterialTheme.typography.bodySmall,
                        placeholder = { Text("Task key (required, e.g. budget-report-q3)", fontSize = 11.sp) },
                    )
                    Spacer(Modifier.height(Spacing.xs))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        taskOutcomes.forEach { outcome ->
                            TextButton(onClick = { selectedOutcome = outcome }) {
                                Text(
                                    (if (selectedOutcome == outcome) "• " else "") + outcomeLabel(outcome),
                                    fontSize = 12.sp,
                                )
                            }
                        }
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(checked = correctionReceived, onCheckedChange = { correctionReceived = it })
                        Text("A correction was received", fontSize = 12.sp)
                    }
                    OutlinedTextField(
                        value = evalNote,
                        onValueChange = { evalNote = it },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        textStyle = MaterialTheme.typography.bodySmall,
                        placeholder = { Text("Note (optional)", fontSize = 11.sp) },
                    )
                    Spacer(Modifier.height(Spacing.xs))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        TextButton(onClick = {
                            onRecordEvaluation(
                                taskKey,
                                selectedOutcome.ifBlank { "unknown" },
                                correctionReceived,
                                evalNote,
                            ) { ok, msg -> evalStatus = msg }
                        }) { Text("Save evaluation", fontSize = 12.sp) }
                        Spacer(Modifier.width(Spacing.sm))
                        evalStatus.ifBlank { null }?.let {
                            Text(it, fontSize = 11.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
        }
    }

    explanation?.let { lines ->
        AlertDialog(
            onDismissRequest = { explanation = null },
            confirmButton = {
                TextButton(onClick = { explanation = null }) { Text("Close") }
            },
            title = {
                Text(
                    if (explanationVerified) "Why — goal verified" else "Why — goal not verified",
                    fontSize = 16.sp,
                )
            },
            text = {
                Column {
                    lines.forEach { line ->
                        Text(line, fontSize = 12.sp)
                        Spacer(Modifier.height(Spacing.xs))
                    }
                }
            },
        )
    }
}
