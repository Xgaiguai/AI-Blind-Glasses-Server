package com.example.blindglassesapp.ui

import android.app.Activity
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import com.example.blindglassesapp.ble.BleConnectionState
import com.example.blindglassesapp.tts.TtsManager
import com.example.blindglassesapp.viewmodel.MainViewModel

/**
 * 功能描述資料類別。
 */
data class AccessibilityFeature(
    val name: String,
    val action: () -> Unit
)

/**
 * 盲人專用全螢幕無障礙功能頁面。
 *
 * 使用 WCAG 規範的「語意大按鈕清單 (Semantic List)」設計，
 * 以 LazyVerticalGrid (2 欄) 呈現所有功能按鈕，完全相容 TalkBack。
 *
 * 取代舊版 pointerInput 多指手勢方案，避免與系統輔助功能衝突。
 */
@Composable
fun AccessibilityScreen(
    viewModel: MainViewModel,
    ttsManager: TtsManager,
    onBack: () -> Unit
) {
    // ── 保留的 ViewModel 狀態 ──
    val bleState by viewModel.bleState.collectAsState()
    val volume by viewModel.currentVolume.collectAsState()
    val isConnected = bleState is BleConnectionState.Connected
    val isVolumeActive by viewModel.isVolumeAdjustmentActive.collectAsState()

    val view = LocalView.current

    // ── 保留的沉浸模式邏輯 ──
    // 進入頁面時自動隱藏導覽列與狀態列（進入沉浸模式，防誤觸）
    DisposableEffect(view) {
        viewModel.setAccessibilityModeActive(true)
        val window = (view.context as? Activity)?.window
        if (window != null) {
            val insetsController = WindowCompat.getInsetsController(window, view)
            insetsController.hide(WindowInsetsCompat.Type.systemBars())
            insetsController.systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE

            onDispose {
                insetsController.show(WindowInsetsCompat.Type.systemBars())
                viewModel.setVolumeAdjustmentActive(false)
                viewModel.setAccessibilityModeActive(false)
            }
        } else {
            onDispose {
                viewModel.setVolumeAdjustmentActive(false)
                viewModel.setAccessibilityModeActive(false)
            }
        }
    }

    // ── 監聽外部退出事件 ──
    LaunchedEffect(Unit) {
        viewModel.closeAccessibilityEvent.collect {
            onBack()
        }
    }

    var showDeviceSheet by remember { mutableStateOf(false) }

    LaunchedEffect(bleState) {
        when (bleState) {
            is BleConnectionState.DevicesFound -> showDeviceSheet = true
            is BleConnectionState.Connected -> {
                showDeviceSheet = false
                ttsManager.speak("眼鏡連線成功")
            }
            is BleConnectionState.Error -> ttsManager.speak((bleState as BleConnectionState.Error).message)
            is BleConnectionState.Disconnected -> ttsManager.speak("眼鏡已斷開連線")
            else -> {}
        }
    }

    // ── 進入頁面時播報說明 ──
    LaunchedEffect(Unit) {
        if (isConnected) {
            ttsManager.speak("已進入盲人模式。畫面上有多個大按鈕，可直接點擊使用各項功能。")
        } else {
            ttsManager.speak("盲人模式。眼鏡尚未連線。請先點選連接眼鏡，或點擊退出按鈕離開此模式。")
        }
    }

    // ── 合併後的功能清單 (allFeatures) ──
    val allFeatures = remember(isConnected, volume) {
        listOf(
            AccessibilityFeature("連接眼鏡") {
                if (isConnected) {
                    ttsManager.speak("眼鏡已連線，不需重複連接")
                } else {
                    ttsManager.speak("開始掃描周圍眼鏡，請稍後")
                    viewModel.startScan()
                }
            },
            // 原 verticalFeatures (4 個)
            AccessibilityFeature("尋找眼鏡") {
                if (isConnected) {
                    val sent = viewModel.sendFindMe()
                    if (sent) ttsManager.speak("找眼鏡")
                    else ttsManager.speak("尋找失敗")
                } else ttsManager.speak("尚未連線")
            },
            AccessibilityFeature("調整音量") {
                if (isConnected) {
                    viewModel.setVolumeAdjustmentActive(true)
                    ttsManager.speak("已進入音量調整模式。現在音量是 ${viewModel.currentVolume.value}。請使用手機側邊音量按鍵調整音量。")
                } else {
                    ttsManager.speak("眼鏡尚未連線")
                }
            },
            AccessibilityFeature("查詢電量") {
                ttsManager.speak("電量百分之百") // 之後可串接真實 API
            },
            AccessibilityFeature("查詢時間") {
                ttsManager.speak("現在時間") // 之後可串接系統時間
            },
            // 原 horizontalFeatures (5 個)
            AccessibilityFeature("環境描述") {
                ttsManager.speak("正在掃描環境") // 之後可串接相機 AI
            },
            AccessibilityFeature("路徑導航") {
                ttsManager.speak("準備導航") // 之後可串接地圖 API
            },
            AccessibilityFeature("人臉辨識") {
                ttsManager.speak("啟動人臉辨識")
            },
            AccessibilityFeature("文字閱讀") {
                ttsManager.speak("啟動文字閱讀")
            },
            AccessibilityFeature("警報模式") {
                ttsManager.speak("發出警報")
            }
        )
    }

    // ── 主 UI ──
    Scaffold(
        containerColor = Color.Black
    ) { innerPadding ->

        if (isVolumeActive) {
            // ━━━━ 音量調整模式：滿版全螢幕按鈕 ━━━━
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innerPadding),
                contentAlignment = Alignment.Center
            ) {
                FilledTonalButton(
                    onClick = {
                        viewModel.setVolumeAdjustmentActive(false)
                        ttsManager.speak("已退出音量調整模式")
                    },
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(16.dp)
                        .semantics {
                            onClick(label = "退出音量調整模式") { true }
                        },
                    shape = MaterialTheme.shapes.extraLarge,
                    colors = ButtonDefaults.filledTonalButtonColors(
                        containerColor = MaterialTheme.colorScheme.primaryContainer,
                        contentColor = MaterialTheme.colorScheme.onPrimaryContainer
                    )
                ) {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center
                    ) {
                        Text(
                            text = "音量調整中",
                            fontSize = 36.sp,
                            fontWeight = FontWeight.ExtraBold,
                            textAlign = TextAlign.Center
                        )
                        Spacer(modifier = Modifier.height(24.dp))
                        Text(
                            text = "目前音量：$volume",
                            fontSize = 28.sp,
                            fontWeight = FontWeight.Bold,
                            textAlign = TextAlign.Center
                        )
                        Spacer(modifier = Modifier.height(24.dp))
                        Text(
                            text = "請按手機實體音量鍵",
                            fontSize = 28.sp,
                            fontWeight = FontWeight.Bold,
                            textAlign = TextAlign.Center
                        )
                        Spacer(modifier = Modifier.height(32.dp))
                        Text(
                            text = "點擊此處退出音量調整",
                            fontSize = 24.sp,
                            fontWeight = FontWeight.Medium,
                            textAlign = TextAlign.Center,
                            color = MaterialTheme.colorScheme.primary
                        )
                    }
                }
            }
        } else {
            // ━━━━ 主要功能清單：大按鈕網格 ━━━━
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innerPadding)
            ) {
                // 標題區域
                Text(
                    text = "盲人模式",
                    fontSize = 32.sp,
                    fontWeight = FontWeight.ExtraBold,
                    color = Color.White,
                    textAlign = TextAlign.Center,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 16.dp, bottom = 8.dp)
                )

                // 連線狀態提示
                if (!isConnected) {
                    Text(
                        text = "⚠ 眼鏡尚未連線",
                        fontSize = 22.sp,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.error,
                        textAlign = TextAlign.Center,
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(bottom = 8.dp)
                    )
                }

                // 功能按鈕網格 (2 欄)
                LazyVerticalGrid(
                    columns = GridCells.Fixed(2),
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                    modifier = Modifier.weight(1f)
                ) {
                    items(allFeatures) { feature ->
                        FilledTonalButton(
                            onClick = { feature.action() },
                            modifier = Modifier
                                .fillMaxWidth()
                                .defaultMinSize(minHeight = 120.dp)
                                .semantics {
                                    onClick(label = "執行${feature.name}功能") { true }
                                },
                            shape = MaterialTheme.shapes.large,
                            colors = ButtonDefaults.filledTonalButtonColors(
                                containerColor = MaterialTheme.colorScheme.secondaryContainer,
                                contentColor = MaterialTheme.colorScheme.onSecondaryContainer
                            )
                        ) {
                            Text(
                                text = feature.name,
                                fontSize = 28.sp,
                                fontWeight = FontWeight.Bold,
                                textAlign = TextAlign.Center
                            )
                        }
                    }
                }

                // ── 退出盲人模式按鈕 ──
                Spacer(modifier = Modifier.height(12.dp))

                FilledTonalButton(
                    onClick = {
                        ttsManager.stop()
                        viewModel.setVolumeAdjustmentActive(false)
                        ttsManager.speak("已退出盲人模式")
                        onBack()
                    },
                    modifier = Modifier
                        .fillMaxWidth()
                        .defaultMinSize(minHeight = 120.dp)
                        .padding(horizontal = 12.dp, vertical = 12.dp)
                        .semantics {
                            onClick(label = "退出盲人模式，返回上一頁") { true }
                        },
                    shape = MaterialTheme.shapes.large,
                    colors = ButtonDefaults.filledTonalButtonColors(
                        containerColor = MaterialTheme.colorScheme.errorContainer,
                        contentColor = MaterialTheme.colorScheme.onErrorContainer
                    )
                ) {
                    Text(
                        text = "退出盲人模式",
                        fontSize = 28.sp,
                        fontWeight = FontWeight.ExtraBold,
                        textAlign = TextAlign.Center
                    )
                }
            }
        }
    }

    // ── 藍牙裝置清單底層表單 ──
    if (showDeviceSheet && bleState is BleConnectionState.DevicesFound) {
        DeviceListSheet(
            devices = (bleState as BleConnectionState.DevicesFound).devices,
            onDeviceSelected = { device ->
                showDeviceSheet = false
                viewModel.connectDevice(device)
            },
            onDismiss = {
                showDeviceSheet = false
                viewModel.dismissDeviceListResults()
            }
        )
    }
}
