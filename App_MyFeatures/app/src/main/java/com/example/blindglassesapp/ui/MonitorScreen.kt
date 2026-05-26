package com.example.blindglassesapp.ui

import android.graphics.Bitmap
import android.util.Log
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.blindglassesapp.network.FamilyEndpoints
import com.example.blindglassesapp.network.FrameRepository
import com.example.blindglassesapp.network.MonitorStateRepository
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MonitorScreen(
    onBack: () -> Unit,
    frameRepo: FrameRepository = FrameRepository(),
    stateRepo: MonitorStateRepository = MonitorStateRepository()
) {
    val scope = rememberCoroutineScope()
    var latestFrame by remember { mutableStateOf<Bitmap?>(null) }
    var monitorState by remember { mutableStateOf<MonitorStateRepository.ServerMonitorState?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var errorMsg by remember { mutableStateOf<String?>(null) }

    suspend fun refresh() {
        isLoading = true
        errorMsg = null
        val bitmap = frameRepo.fetchLatestFrame()
        val state = stateRepo.fetchMonitorState()
        latestFrame = bitmap
        monitorState = state
        if (bitmap == null && state == null) {
            errorMsg = "無法取得資料，請確認眼鏡已連線至網路並啟動影像串流。"
        }
        isLoading = false
    }

    // 啟動時自動拉取一次，並每 3 秒更新
    LaunchedEffect(Unit) {
        while (true) {
            refresh()
            delay(3000L)
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text("眼鏡遠端監看", fontWeight = FontWeight.Bold)
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "返回")
                    }
                },
                actions = {
                    IconButton(onClick = { scope.launch { refresh() } }) {
                        Icon(Icons.Default.Refresh, contentDescription = "重新整理")
                    }
                }
            )
        }
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(innerPadding)
                .padding(16.dp)
        ) {
            // 影像顯示區
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(240.dp)
                    .background(Color.Black),
                contentAlignment = Alignment.Center
            ) {
                when {
                    isLoading && latestFrame == null -> {
                        CircularProgressIndicator(color = Color.White)
                    }
                    latestFrame != null -> {
                        Image(
                            bitmap = latestFrame!!.asImageBitmap(),
                            contentDescription = "眼鏡即時影像",
                            modifier = Modifier.fillMaxSize(),
                            contentScale = ContentScale.Fit
                        )
                    }
                    else -> {
                        Text(
                            text = "無法取得影像",
                            color = Color.White,
                            style = MaterialTheme.typography.bodyMedium
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            // 狀態資訊
            if (errorMsg != null) {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.errorContainer
                    )
                ) {
                    Text(
                        text = errorMsg!!,
                        modifier = Modifier.padding(16.dp),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onErrorContainer
                    )
                }
            }

            monitorState?.let { state ->
                Spacer(modifier = Modifier.height(12.dp))
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text(
                            "伺服器狀態",
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.Bold
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        MonitorInfoRow("影像串流", if (state.isStreaming) "進行中" else "未串流")
                        MonitorInfoRow("幀率 (FPS)", String.format("%.1f", state.fps))
                        MonitorInfoRow("解析度", "${state.width} × ${state.height}")
                        MonitorInfoRow("線上觀看人數", state.activeViewers.toString())
                        MonitorInfoRow("裝置連線", if (state.deviceConnected) "已連線 (${state.deviceIp})" else "未連線")
                    }
                }
            }

            Spacer(modifier = Modifier.height(12.dp))
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        "網頁版監看連結",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = FamilyEndpoints.MONITOR_PAGE,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }
    }
}

@Composable
private fun MonitorInfoRow(label: String, value: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 2.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(text = value, style = MaterialTheme.typography.bodySmall)
    }
}
