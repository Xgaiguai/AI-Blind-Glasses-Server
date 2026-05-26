package com.example.blindglassesapp.ui

import android.annotation.SuppressLint
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.Uri
import android.webkit.WebView
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedCard
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.contentColorFor
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.example.blindglassesapp.network.FamilyEndpoints
import com.example.blindglassesapp.network.FrameRepository
import com.example.blindglassesapp.network.MonitorStateRepository
import com.example.blindglassesapp.network.MonitorUiSnapshot
import com.example.blindglassesapp.ui.theme.AppThemePreference
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.Locale

private val MONITOR_BASE_URL = FamilyEndpoints.BASE.trimEnd('/')

private fun Context.hasInternetConnectivity(): Boolean {
    val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
    val network = cm.activeNetwork ?: return false
    val caps = cm.getNetworkCapabilities(network) ?: return false
    return caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
}

private fun monitorPageUrl() = "$MONITOR_BASE_URL/monitor"
private fun streamUrl() = "$MONITOR_BASE_URL/stream"

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MonitorScreen(
    onBack: () -> Unit,
    themePreference: AppThemePreference,
    onThemePreferenceChange: (AppThemePreference) -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val outline = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant)
    val cardShape = RoundedCornerShape(16.dp)
    val scroll = rememberScrollState()
    val snackbarHostState = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()

    var isOnline by remember { mutableStateOf(context.hasInternetConnectivity()) }
    var hasReceivedFrame by remember { mutableStateOf(false) }
    var hasReceivedState by remember { mutableStateOf(false) }

    var currentFrame by remember { mutableStateOf<Bitmap?>(null) }
    var frameSource by remember { mutableStateOf("連線中…") }

    var monitorSnap by remember {
        mutableStateOf(MonitorUiSnapshot(motionLabel = "…", mapUrl = null, latitude = null, longitude = null))
    }
    var stateSource by remember { mutableStateOf("連線中…") }
    var serverHealthy by remember { mutableStateOf<Boolean?>(null) }

    val frameRepo = remember {
        FrameRepository(baseUrl = MONITOR_BASE_URL, httpPollIntervalMs = 200L)
    }
    val stateRepo = remember { MonitorStateRepository(MONITOR_BASE_URL) }

    // ── 網路監聽 (Preserved) ──
    DisposableEffect(context) {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                isOnline = context.hasInternetConnectivity()
            }

            override fun onLost(network: Network) {
                isOnline = context.hasInternetConnectivity()
                if (!isOnline) {
                    scope.launch {
                        snackbarHostState.showSnackbar("無網路連線，無法取得即時資料")
                    }
                }
            }

            override fun onCapabilitiesChanged(network: Network, caps: NetworkCapabilities) {
                val online = caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                isOnline = online
            }
        }
        cm.registerDefaultNetworkCallback(callback)
        isOnline = context.hasInternetConnectivity()
        if (!isOnline) {
            scope.launch {
                snackbarHostState.showSnackbar("無網路連線，無法取得即時資料")
            }
        }
        onDispose {
            cm.unregisterNetworkCallback(callback)
        }
    }

    // ── 畫面超時提示 (Preserved) ──
    LaunchedEffect(hasReceivedFrame, isOnline) {
        if (hasReceivedFrame) return@LaunchedEffect
        delay(20_000)
        if (!hasReceivedFrame && context.hasInternetConnectivity()) {
            snackbarHostState.showSnackbar("尚未取得畫面，請確認網路或稍後再試")
        }
    }

    // ── 影像串流 WebSocket / HTTP (Preserved) ──
    LaunchedEffect(Unit) {
        var wsOk = false
        try {
            frameRepo.wsFrameStream()
                .catch { }
                .collect { bitmap ->
                    if (!wsOk) {
                        wsOk = true
                        frameSource = "影像：WebSocket"
                    }
                    if (bitmap != null) {
                        currentFrame = bitmap
                        hasReceivedFrame = true
                    }
                }
        } catch (_: Exception) {
        }
        if (!wsOk) {
            frameSource = "影像：HTTP"
            frameRepo.httpFrameStream()
                .catch { e ->
                    frameSource = "影像失敗：${e.message}"
                }
                .collect { bitmap ->
                    if (bitmap != null) {
                        currentFrame = bitmap
                        hasReceivedFrame = true
                    }
                }
        }
    }

    // ── 狀態串流 WebSocket / HTTP (Preserved) ──
    LaunchedEffect(Unit) {
        serverHealthy = withContext(Dispatchers.IO) { stateRepo.checkHealth() }
        try {
            stateSource = "狀態：WebSocket"
            stateRepo.wsUiStateFlow().collect { snap ->
                monitorSnap = snap
                hasReceivedState = true
            }
        } catch (_: Throwable) {
        }
        stateSource = "狀態：HTTP"
        stateRepo.httpStatePollFlow().collect { snap ->
            monitorSnap = snap
            hasReceivedState = true
        }
    }

    // ── openUrl (Preserved) ──
    fun openUrl(url: String) {
        context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)))
    }

    // ── 地圖與座標衍生值 (Preserved) ──
    val la = monitorSnap.latitude
    val lo = monitorSnap.longitude
    val embedUrl = remember(la, lo) {
        if (la != null && lo != null) {
            String.format(Locale.US, "https://www.google.com/maps?q=%f,%f&z=17&output=embed", la, lo)
        } else null
    }
    val coordsText = when {
        la != null && lo != null ->
            String.format(Locale.US, "%.6f, %.6f", la, lo)
        else -> "尚無 GPS 座標"
    }

    // ── 狀態文字：去除技術名詞，只顯示「已同步」或「載入中」──
    val frameStatusText = when {
        !isOnline -> "畫面：無網路"
        hasReceivedFrame -> "畫面：已取得"
        else -> "畫面：載入中…"
    }
    val stateStatusText = when {
        !isOnline -> "狀態：無網路"
        hasReceivedState -> "狀態：已同步"
        else -> "狀態：載入中…"
    }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHostState) },
        topBar = {
            TopAppBar(
                title = { Text("即時監看", style = MaterialTheme.typography.titleLarge) },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface,
                    scrolledContainerColor = MaterialTheme.colorScheme.surfaceContainerHigh,
                    navigationIconContentColor = MaterialTheme.colorScheme.onSurface,
                    titleContentColor = MaterialTheme.colorScheme.onSurface,
                    actionIconContentColor = MaterialTheme.colorScheme.onSurface,
                ),
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Text("←", style = MaterialTheme.typography.titleLarge)
                    }
                },
                actions = {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.padding(end = 4.dp),
                    ) {
                        val healthy = serverHealthy
                        if (healthy != null) {
                            Box(
                                modifier = Modifier
                                    .size(8.dp)
                                    .clip(CircleShape)
                                    .background(
                                        if (healthy) {
                                            MaterialTheme.colorScheme.primary
                                        } else {
                                            MaterialTheme.colorScheme.error
                                        },
                                    ),
                            )
                            Spacer(Modifier.width(6.dp))
                        }
                        Text(
                            text = when (healthy) {
                                true -> "系統連線正常"
                                false -> "設備連線異常"
                                null -> ""
                            },
                            style = MaterialTheme.typography.labelSmall,
                        )
                        Spacer(Modifier.width(4.dp))
                        ThemePreferenceOverflowMenu(
                            current = themePreference,
                            onChange = onThemePreferenceChange,
                        )
                    }
                },
            )
        },
        modifier = modifier,
    ) { innerPadding ->
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(innerPadding)
                .verticalScroll(scroll)
                .padding(horizontal = 16.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            // ── 無網路橫幅 ──
            if (!isOnline) {
                OutlinedCard(
                    shape = cardShape,
                    border = BorderStroke(1.dp, MaterialTheme.colorScheme.error),
                    colors = CardDefaults.outlinedCardColors(
                        containerColor = MaterialTheme.colorScheme.errorContainer,
                    ),
                ) {
                    Text(
                        text = "無網路連線",
                        modifier = Modifier.padding(12.dp),
                        style = MaterialTheme.typography.titleSmall,
                        color = MaterialTheme.colorScheme.onErrorContainer,
                    )
                }
            }

            // ══════════════════════════════════════════════════════
            // 區塊一：即時影像中樞 (Hero Video Card)
            // 影像 + 連線狀態整合在同一張卡片
            // ══════════════════════════════════════════════════════
            OutlinedCard(
                modifier = Modifier.fillMaxWidth(),
                shape = cardShape,
                border = outline,
            ) {
                // 影像畫面
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(260.dp)
                        .background(Color.Black)
                        .clip(RoundedCornerShape(topStart = 16.dp, topEnd = 16.dp)),
                    contentAlignment = Alignment.Center,
                ) {
                    if (currentFrame != null) {
                        Image(
                            bitmap = currentFrame!!.asImageBitmap(),
                            contentDescription = "即時影像",
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(260.dp),
                            contentScale = ContentScale.Fit,
                        )
                    } else {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            CircularProgressIndicator(
                                color = MaterialTheme.colorScheme.primary,
                                trackColor = contentColorFor(Color.Black).copy(alpha = 0.28f),
                            )
                            Spacer(Modifier.height(12.dp))
                            Text(
                                if (isOnline) "正在抓取畫面…" else "無網路，無法載入",
                                style = MaterialTheme.typography.bodyMedium,
                                color = contentColorFor(Color.Black),
                            )
                        }
                    }
                }

                // 連線狀態列（緊貼影像下方，同一張卡片內）
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 12.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    // 畫面狀態
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            modifier = Modifier
                                .size(8.dp)
                                .clip(CircleShape)
                                .background(
                                    when {
                                        !isOnline -> MaterialTheme.colorScheme.error
                                        hasReceivedFrame -> MaterialTheme.colorScheme.primary
                                        else -> MaterialTheme.colorScheme.outlineVariant
                                    },
                                ),
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            text = frameStatusText,
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    // 狀態同步
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            modifier = Modifier
                                .size(8.dp)
                                .clip(CircleShape)
                                .background(
                                    when {
                                        !isOnline -> MaterialTheme.colorScheme.error
                                        hasReceivedState -> MaterialTheme.colorScheme.primary
                                        else -> MaterialTheme.colorScheme.outlineVariant
                                    },
                                ),
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(
                            text = stateStatusText,
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }

            // ══════════════════════════════════════════════════════
            // 區塊二：綜合地理資訊板 (Location Dashboard)
            // 移動狀態 + GPS 座標 + 地圖預覽 + 外部開啟按鈕
            // ══════════════════════════════════════════════════════
            OutlinedCard(
                modifier = Modifier.fillMaxWidth(),
                shape = cardShape,
                border = outline,
            ) {
                Column(Modifier.padding(16.dp)) {
                    // ── 移動狀態 ──
                    Text(
                        text = "移動狀態",
                        style = MaterialTheme.typography.titleSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(Modifier.height(4.dp))
                    Text(
                        text = monitorSnap.motionLabel,
                        style = MaterialTheme.typography.titleLarge,
                        modifier = Modifier.fillMaxWidth(),
                    )

                    Spacer(Modifier.height(12.dp))

                    // ── GPS 座標 ──
                    Text(
                        text = "目前位置",
                        style = MaterialTheme.typography.titleSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(Modifier.height(4.dp))
                    Text(
                        text = coordsText,
                        style = MaterialTheme.typography.bodyLarge,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }

                HorizontalDivider(
                    color = MaterialTheme.colorScheme.outlineVariant,
                    thickness = 1.dp,
                )

                // ── 地圖預覽 (WebView) ──
                Column(Modifier.padding(16.dp)) {
                    Text(
                        text = "地圖預覽",
                        style = MaterialTheme.typography.titleSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(Modifier.height(8.dp))
                    if (embedUrl != null) {
                        key(embedUrl) {
                            @SuppressLint("SetJavaScriptEnabled")
                            AndroidView(
                                factory = { ctx ->
                                    WebView(ctx).apply {
                                        settings.javaScriptEnabled = true
                                        settings.domStorageEnabled = true
                                        loadUrl(embedUrl)
                                    }
                                },
                                update = { wv -> wv.loadUrl(embedUrl) },
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .height(220.dp)
                                    .clip(RoundedCornerShape(12.dp)),
                            )
                        }
                    } else {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .height(120.dp)
                                .clip(RoundedCornerShape(12.dp))
                                .background(MaterialTheme.colorScheme.surfaceVariant),
                            contentAlignment = Alignment.Center,
                        ) {
                            Text(
                                "取得座標後顯示地圖",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                textAlign = TextAlign.Center,
                                modifier = Modifier.padding(16.dp),
                            )
                        }
                    }
                }

                HorizontalDivider(
                    color = MaterialTheme.colorScheme.outlineVariant,
                    thickness = 1.dp,
                )

                // ── 在 Google 地圖開啟按鈕 ──
                OutlinedButton(
                    onClick = { monitorSnap.mapUrl?.let { openUrl(it) } },
                    enabled = !monitorSnap.mapUrl.isNullOrBlank(),
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(56.dp)
                        .padding(horizontal = 16.dp, vertical = 8.dp),
                    shape = cardShape,
                ) {
                    Text("在 Google 地圖中開啟")
                }
                Spacer(Modifier.height(8.dp))
            }

            // ══════════════════════════════════════════════════════
            // 底部操作按鈕
            // ══════════════════════════════════════════════════════
            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                FilledTonalButton(
                    onClick = { openUrl(monitorPageUrl()) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(56.dp),
                    shape = cardShape,
                ) {
                    Text("開啟網頁版儀表板", style = MaterialTheme.typography.titleSmall)
                }
                OutlinedButton(
                    onClick = { openUrl(streamUrl()) },
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(56.dp),
                    shape = cardShape,
                ) {
                    Text("開啟獨立影像視窗", style = MaterialTheme.typography.titleSmall)
                }
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}
