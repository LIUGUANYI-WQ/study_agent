/* ========== 欢迎页 ========== */
const WELCOME_IMG = 'https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=' + 
    encodeURIComponent('cute anime schoolgirl in JK uniform with long hair waving hello, soft pastel colors, detailed anime style, white background, friendly smile, holding a book, kawaii, high quality illustration') + 
    '&image_size=portrait_4_3';

const BG_IMG = 'https://trae-api-cn.mchost.guru/api/ide/v1/text_to_image?prompt=' + 
    encodeURIComponent('cozy study room with cute anime girl studying at desk by the window, books and plants, soft warm lighting, watercolor anime style, pastel colors, peaceful healing atmosphere, wide landscape') + 
    '&image_size=landscape_16_9';

function initWelcome() {
    const page = document.getElementById('welcome-page');
    const btn = document.getElementById('btn-enter');

    // 加载欢迎页图片
    const welcomeImg = document.getElementById('welcome-img');
    welcomeImg.onload = () => welcomeImg.classList.add('loaded');
    welcomeImg.src = WELCOME_IMG;

    // 加载主背景（预加载）
    const appBg = document.getElementById('app-bg');
    const bgImg = new Image();
    bgImg.onload = () => {
        appBg.style.backgroundImage = `url(${BG_IMG})`;
        appBg.classList.add('loaded');
    };
    bgImg.src = BG_IMG;

    // 生成浮动粒子
    for (let i = 0; i < 20; i++) {
        const p = document.createElement('div');
        p.className = 'particle';
        const size = Math.random() * 12 + 4;
        p.style.cssText = `
            width:${size}px; height:${size}px;
            left:${Math.random()*100}%; top:${Math.random()*100+100}%;
            animation-duration:${Math.random()*8+6}s;
            animation-delay:${Math.random()*4}s;
        `;
        page.appendChild(p);
    }

    btn.addEventListener('click', () => {
        page.classList.add('hidden');
        setTimeout(() => page.style.display = 'none', 600);
    });
}

/* ========== Toast 通知 ========== */
function showToast(msg, type = 'info') {
    const container = document.getElementById('toast-container') || createToastContainer();
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(40px)';
        toast.style.transition = '.3s';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

function createToastContainer() {
    const c = document.createElement('div');
    c.id = 'toast-container';
    c.className = 'toast-container';
    document.body.appendChild(c);
    return c;
}

/* ========== 页面切换 ========== */
function switchPage(name) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.getElementById('page-' + name).classList.add('active');
    document.querySelector(`.nav-item[data-page="${name}"]`).classList.add('active');
    if (name === 'tasks') loadTasks();
}

/* ========== 统计 ========== */
async function loadStats() {
    try {
        const res = await fetch('/api/stats');
        const data = await res.json();
        document.getElementById('stat-tasks').textContent = data.total_tasks;
        document.getElementById('stat-reviews').textContent = data.total_reviews;
        document.getElementById('stat-records').textContent = data.total_records;
        document.getElementById('stat-done').textContent = data.completed_tasks;
    } catch (e) { console.error(e); }
}

/* ========== 任务管理 ========== */
let tasksData = [];
let expandedTaskIndex = -1;
let currentQuizParams = null;

/* ========== 复习计划 ========== */
let planData = null;
let planExpandedTaskKey = null;
let planKnowledgePoints = {};

async function loadTasks() {
    try {
        const res = await fetch('/api/tasks');
        tasksData = await res.json();
        renderTasks();
    } catch (e) { console.error(e); }
}

function renderTasks() {
    const list = document.getElementById('task-list');
    const empty = document.getElementById('tasks-empty');
    if (!tasksData.length) {
        list.innerHTML = '';
        empty.style.display = 'block';
        return;
    }
    empty.style.display = 'none';
    list.innerHTML = tasksData.map((t, i) => {
        const masteryClass = t.mastery === '生疏' ? 'low' : t.mastery === '一般' ? 'mid' : '';
        const isExpanded = expandedTaskIndex === i;
        const kps = taskKnowledgePoints[i];
        let kpHtml = '';
        if (isExpanded) {
            if (!kps || kps.loading) {
                kpHtml = `<div class="kp-loading">⏳ 加载知识点中...</div>`;
            } else {
                const kpList = kps.kps || [];
                const source = kps.source || 'matched';
                if (kpList.length === 0) {
                    kpHtml = `<div class="kp-loading" style="color: var(--text2);">暂无相关知识点</div>`;
                } else {
                    kpHtml = `<div class="kp-list">
                        ${kpList.slice(0, 6).map((kp, ki) => `
                            <div class="kp-list-item">
                                <div class="kp-list-info">
                                    <div class="kp-list-name">
                                        <span class="kp-list-type">${kp.type || '知识点'}</span>
                                        ${escapeHtml(kp.name)}
                                        <span class="kp-source-tag ${source}">${source === 'linked' ? '强关联' : '智能匹配'}</span>
                                    </div>
                                    <div class="kp-list-desc">${escapeHtml(kp.description || '')}</div>
                                </div>
                                <div style="display: flex; gap: 6px; align-items: center;">
                                    <button class="kp-explain-btn" onclick="explainKnowledgePoint(${i}, ${ki})">讲解</button>
                                    <button class="kp-quiz-btn" onclick="quizSingleKnowledgePoint(${i}, ${ki}, event)">考察</button>
                                    ${source === 'linked' ? `<button class="kp-unlink-btn" onclick="unlinkKnowledgePoint(${i}, ${ki}, event)">✕</button>` : ''}
                                </div>
                            </div>
                        `).join('')}
                    </div>`;
                }
                kpHtml += `<button class="kp-add-link-btn" onclick="openKpLinkModal(${i}, event)">+ 关联知识点</button>`;
            }
        }
        return `<li class="task-item ${isExpanded ? 'expanded' : ''}">
            <div class="task-main" onclick="toggleTaskDetail(${i})">
                <div class="task-priority">${t.priority || 0}</div>
                <div class="task-info">
                    <div class="task-name">${escapeHtml(t.task)}</div>
                    <div class="task-meta">
                        <span class="tag tag-category">${t.category}</span>
                        <span class="tag tag-mastery ${masteryClass}">${t.mastery}</span>
                        <span class="tag tag-deadline">截止 ${t.deadline}</span>
                        <span>复习 ${t.review_count || 0} 次</span>
                    </div>
                </div>
                <div class="task-expand-icon">${isExpanded ? '▲' : '▼'}</div>
            </div>
            ${isExpanded ? `
            <div class="task-detail">
                <div class="task-detail-section">
                    <div class="task-detail-title">📋 任务信息</div>
                    <div class="task-detail-grid">
                        <div><span class="task-detail-label">分类</span><span>${t.category}</span></div>
                        <div><span class="task-detail-label">掌握程度</span><span>${t.mastery}</span></div>
                        <div><span class="task-detail-label">截止日期</span><span>${t.deadline}</span></div>
                        <div><span class="task-detail-label">优先级</span><span>${t.priority || 0}</span></div>
                        <div><span class="task-detail-label">已复习</span><span>${t.review_count || 0} 次</span></div>
                        <div><span class="task-detail-label">预估时长</span><span>${t.estimated_hours || 0} 小时</span></div>
                    </div>
                </div>
                <div class="task-detail-section">
                    <div class="task-detail-title">📚 相关知识点</div>
                    ${kpHtml}
                </div>
                <div class="task-detail-actions">
                    <button class="btn btn-primary" onclick="startQuizFromTask(${i})">🎯 开始考察这个任务</button>
                    <button class="btn btn-success" onclick="markReviewed(${i})">✅ 标记已复习</button>
                    <button class="btn btn-danger" onclick="deleteTask(${i})">🗑️ 删除</button>
                </div>
            </div>
            ` : ''}
        </li>`;
    }).join('');
}

let taskKnowledgePoints = {};  // 缓存每个任务的知识点 { kps: [], source: 'linked'|'matched' }
let currentLinkTaskIndex = -1;  // 当前正在关联知识点的任务索引
let allKnowledgePoints = [];    // 所有知识点列表
let selectedKpIds = new Set();  // 选中的知识点ID

function toggleTaskDetail(index) {
    if (expandedTaskIndex === index) {
        expandedTaskIndex = -1;
    } else {
        expandedTaskIndex = index;
        // 展开时加载知识点
        loadTaskKnowledgePoints(index);
    }
    renderTasks();
}

async function loadTaskKnowledgePoints(index) {
    if (taskKnowledgePoints[index]) return;  // 已缓存
    taskKnowledgePoints[index] = { loading: true };
    try {
        const res = await fetch(`/api/task/${index}/knowledge-points`);
        const data = await res.json();
        if (data.knowledge_points) {
            taskKnowledgePoints[index] = {
                kps: data.knowledge_points,
                source: data.source || 'matched'
            };
            if (expandedTaskIndex === index) {
                renderTasks();  // 重新渲染更新知识点
            }
        }
    } catch (e) {
        console.error('加载知识点失败:', e);
        taskKnowledgePoints[index] = { kps: [], source: 'matched' };
    }
}

async function startQuizFromTask(index) {
    const task = tasksData[index];
    if (!task) return;
    currentQuizParams = { task_id: task.id, task_index: index, title: task.task, source_page: 'tasks' };
    switchPage('quiz');
    const container = document.getElementById('quiz-container');
    container.innerHTML = `<div class="plan-loading"><div class="spinner"></div><p style="margin-top:12px;">正在为「${escapeHtml(task.task)}」出题...</p></div>`;

    try {
        const res = await fetch('/api/quiz/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(currentQuizParams)
        });
        if (!res.ok) {
            const err = await res.json();
            container.innerHTML = `<p style="color:var(--red)">${err.error || '请求失败'}</p>`;
            return;
        }
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';
        let finalData = null;
        let bubble = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.type === 'text') {
                        if (!bubble) {
                            container.innerHTML = '';
                            const div = document.createElement('div');
                            div.className = 'quiz-bubble';
                            div.id = 'quiz-bubble';
                            container.appendChild(div);
                            bubble = div;
                        }
                        fullText += data.content;
                        bubble.textContent = fullText;
                        container.scrollTop = container.scrollHeight;
                    } else if (data.type === 'done') {
                        finalData = data;
                    }
                } catch (e) { }
            }
        }

        if (finalData) {
            renderQuizQuestionWithInput(finalData.question);
        } else if (!fullText) {
            container.innerHTML = `<p style="color:var(--red)">出题失败</p>`;
        }
    } catch (e) {
        container.innerHTML = `<p style="color:var(--red)">请求失败: ${e.message}</p>`;
    }
}

function showAddTask() { document.getElementById('add-task-form').style.display = 'block'; }
function hideAddTask() { document.getElementById('add-task-form').style.display = 'none'; }

async function submitTask() {
    const name = document.getElementById('task-name').value.trim();
    const deadline = document.getElementById('task-deadline').value;
    if (!name || !deadline) { showToast('请填写任务名称和截止日期', 'error'); return; }
    try {
        const res = await fetch('/api/tasks', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                task_name: name, deadline,
                category: document.getElementById('task-category').value,
                mastery: document.getElementById('task-mastery').value,
                estimated_hours: document.getElementById('task-hours').value,
            })
        });
        const data = await res.json();
        showToast(data.message, 'success');
        hideAddTask();
        loadTasks();
        loadStats();
        document.getElementById('task-name').value = '';
    } catch (e) { showToast('添加失败: ' + e, 'error'); }
}

async function markReviewed(idx) {
    try {
        const res = await fetch(`/api/tasks/${idx}/review`, { method: 'POST' });
        const data = await res.json();
        showToast(data.message, 'success');
        loadTasks();
        loadStats();
    } catch (e) { showToast('操作失败', 'error'); }
}

async function deleteTask(idx) {
    if (!confirm('确定要删除这个任务吗？')) return;
    try {
        const res = await fetch(`/api/tasks/${idx}`, { method: 'DELETE' });
        const data = await res.json();
        showToast(data.message, 'success');
        loadTasks();
        loadStats();
    } catch (e) { showToast('删除失败', 'error'); }
}

/* ========== 学习记录（对话式） ========== */
let recordChatHistory = [];
let currentRecordData = null;
let recordChatSending = false;
let newTagInput = '';

function addRecordMsg(role, text) {
    const box = document.getElementById('record-chat-messages');
    const div = document.createElement('div');
    div.className = `record-msg ${role}`;
    div.innerHTML = `<div class="record-msg-avatar">${role === 'user' ? '😊' : '🤖'}</div><div class="record-msg-bubble">${escapeHtml(text)}</div>`;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
    return div.querySelector('.record-msg-bubble');
}

function cleanRecordReply(text) {
    let cleaned = text;
    cleaned = cleaned.replace(/```json[\s\S]*?```/g, '');
    cleaned = cleaned.replace(/```[\s\S]*?```/g, '');
    cleaned = cleaned.replace(/\n{3,}/g, '\n\n');
    cleaned = cleaned.trim();
    return cleaned;
}

async function sendRecordChat() {
    if (recordChatSending) return;
    const input = document.getElementById('record-chat-input');
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    addRecordMsg('user', text);
    recordChatSending = true;

    const btn = document.getElementById('btn-record-send');
    btn.textContent = '发送中...';
    btn.disabled = true;

    // 如果已有记录，先把新内容追加到raw_content（确保内容完整）
    if (currentRecordData && currentRecordData.raw_content) {
        currentRecordData.raw_content = currentRecordData.raw_content + '\n' + text;
    }

    try {
        const res = await fetch('/api/record-chat', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: text,
                history: recordChatHistory,
                current_record: currentRecordData
            })
        });
        if (!res.ok) {
            const err = await res.json();
            addRecordMsg('assistant', '出错了: ' + (err.error || '未知错误'));
            return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';
        let finalData = null;
        let bubble = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.type === 'text') {
                        if (!bubble) {
                            bubble = addRecordMsg('assistant', '');
                        }
                        fullText += data.content;
                        bubble.textContent = cleanRecordReply(fullText);
                        document.getElementById('record-chat-messages').scrollTop =
                            document.getElementById('record-chat-messages').scrollHeight;
                    } else if (data.type === 'done') {
                        finalData = data;
                    }
                } catch (e) { }
            }
        }

        recordChatHistory.push({ user: text, assistant: fullText });

        if (finalData && finalData.record) {
            currentRecordData = finalData.record;

            // 确保raw_content包含所有用户输入的内容（兜底）
            const allUserInputs = recordChatHistory.map(h => h.user).join('\n');
            if (currentRecordData.raw_content) {
                // 检查是否包含最新的用户输入，如果没有就追加
                if (!currentRecordData.raw_content.includes(text)) {
                    currentRecordData.raw_content = currentRecordData.raw_content + '\n' + text;
                }
            } else {
                currentRecordData.raw_content = allUserInputs;
            }

            renderRecordEditor(currentRecordData);
            document.getElementById('btn-save-record').style.display = 'block';
        }

        if (!fullText && !bubble) {
            addRecordMsg('assistant', '(无回复)');
        }
    } catch (e) {
        addRecordMsg('assistant', '请求失败: ' + e.message);
    }
    recordChatSending = false;
    btn.textContent = '发送';
    btn.disabled = false;
    input.focus();
}

function renderRecordEditor(record) {
    const body = document.getElementById('record-editor-body');
    const kps = record.knowledge_points || [];
    const tags = record.tags || [];

    let html = `
    <div class="editor-section">
        <div class="editor-section-title"><span class="section-icon">📝</span>学习内容</div>
        <textarea class="editor-textarea" id="edit-raw-content" oninput="updateRecordField('raw_content', this.value)">${escapeHtml(record.raw_content || '')}</textarea>
    </div>

    <div class="editor-section">
        <div class="editor-section-title"><span class="section-icon">💡</span>核心要点总结</div>
        <textarea class="editor-textarea" id="edit-summary" style="min-height:50px;" oninput="updateRecordField('summary', this.value)">${escapeHtml(record.summary || '')}</textarea>
    </div>

    <div class="editor-section">
        <div class="editor-section-title"><span class="section-icon">⭐</span>质量评分
            <span class="quality-score-value" id="quality-score-display">${record.quality_score || 0}</span>
        </div>
        <div class="quality-score-row">
            <input type="range" min="0" max="100" value="${record.quality_score || 0}" 
                   id="edit-quality-score" oninput="updateQualityScore(this.value)">
        </div>
        <input type="text" class="editor-input" style="margin-top:8px;" id="edit-quality-comment" 
               placeholder="质量评价说明" value="${escapeHtml(record.quality_comment || '')}"
               oninput="updateRecordField('quality_comment', this.value)">
    </div>

    <div class="editor-section">
        <div class="editor-section-title"><span class="section-icon">✅❌</span>正误判断</div>
        <div class="correct-mistake-section">
            <div>
                <div class="cm-subtitle correct">✅ 理解正确的点</div>
                <div class="correct-list" id="correct-list">
                    ${(record.correct_points && record.correct_points.length > 0) 
                        ? record.correct_points.map((cp, i) => `
                            <div class="correct-item">${escapeHtml(cp)}</div>
                        `).join('')
                        : '<div class="cm-empty">暂无</div>'
                    }
                </div>
            </div>
            <div>
                <div class="cm-subtitle mistake">❌ 错误/待改进的点</div>
                <div class="mistake-list" id="mistake-list">
                    ${(record.mistakes && record.mistakes.length > 0)
                        ? record.mistakes.map((m, i) => `
                            <div class="mistake-item">
                                <div class="mistake-content">${escapeHtml(m.content || m)}</div>
                                ${m.explanation ? `<div class="mistake-explanation">${escapeHtml(m.explanation)}</div>` : ''}
                            </div>
                        `).join('')
                        : '<div class="cm-empty">没有发现错误，很棒！</div>'
                    }
                </div>
            </div>
        </div>
    </div>

    <div class="editor-section">
        <div class="editor-section-title"><span class="section-icon">🎯</span>掌握程度</div>
        <div class="mastery-selector" id="mastery-selector">
            <div class="mastery-option ${record.mastery_level === '生疏' ? 'active' : ''}" onclick="setMastery('生疏')">生疏</div>
            <div class="mastery-option ${record.mastery_level === '一般' ? 'active' : ''}" onclick="setMastery('一般')">一般</div>
            <div class="mastery-option ${record.mastery_level === '熟悉' ? 'active' : ''}" onclick="setMastery('熟悉')">熟悉</div>
            <div class="mastery-option ${record.mastery_level === '精通' ? 'active' : ''}" onclick="setMastery('精通')">精通</div>
        </div>
    </div>

    <div class="editor-section">
        <div class="editor-section-title"><span class="section-icon">📚</span>知识点 (${kps.length})</div>
        <div class="kp-editor-list" id="kp-editor-list">
            ${kps.map((kp, i) => renderKpEditorItem(kp, i)).join('')}
        </div>
        <button class="kp-add-btn" onclick="addKpItem()">+ 添加知识点</button>
    </div>

    <div class="editor-section">
        <div class="editor-section-title"><span class="section-icon">🏷️</span>标签</div>
        <div class="tag-editor-list" id="tag-editor-list">
            ${tags.map((t, i) => renderTagEditorItem(t, i)).join('')}
        </div>
        <div class="tag-editor-input">
            <input type="text" class="editor-input" id="new-tag-input" placeholder="输入新标签..." onkeydown="if(event.key==='Enter')addTag()">
            <button class="btn btn-sm btn-primary" onclick="addTag()">添加</button>
        </div>
    </div>

    <div class="editor-section">
        <div class="editor-section-title"><span class="section-icon">🔧</span>改进建议</div>
        <div id="suggestions-editor">
            ${(record.improvement_suggestions || []).map((s, i) => renderSuggestionItem(s, i)).join('')}
        </div>
        <button class="kp-add-btn" onclick="addSuggestionItem()">+ 添加建议</button>
    </div>
    `;

    body.innerHTML = html;
}

function renderKpEditorItem(kp, index) {
    return `
    <div class="kp-editor-item" data-index="${index}">
        <button class="kp-editor-remove" onclick="removeKpItem(${index})" title="删除">×</button>
        <div class="kp-editor-item-header">
            <input type="text" class="editor-input" placeholder="知识点名称" value="${escapeHtml(kp.name || '')}"
                   oninput="updateKpField(${index}, 'name', this.value)">
            <select class="editor-select" onchange="updateKpField(${index}, 'type', this.value)">
                <option value="概念" ${kp.type === '概念' ? 'selected' : ''}>概念</option>
                <option value="原理" ${kp.type === '原理' ? 'selected' : ''}>原理</option>
                <option value="方法" ${kp.type === '方法' ? 'selected' : ''}>方法</option>
                <option value="工具" ${kp.type === '工具' ? 'selected' : ''}>工具</option>
                <option value="案例" ${kp.type === '案例' ? 'selected' : ''}>案例</option>
                <option value="其他" ${kp.type === '其他' ? 'selected' : ''}>其他</option>
            </select>
        </div>
        <textarea class="editor-textarea" placeholder="知识点描述" style="min-height:40px;font-size:12px;"
                  oninput="updateKpField(${index}, 'description', this.value)">${escapeHtml(kp.description || '')}</textarea>
    </div>`;
}

function renderTagEditorItem(tag, index) {
    return `
    <span class="tag-editor-item">
        ${escapeHtml(tag)}
        <button class="tag-editor-remove" onclick="removeTag(${index})" title="删除">×</button>
    </span>`;
}

function renderSuggestionItem(suggestion, index) {
    return `
    <div class="kp-editor-item" style="margin-bottom:6px;">
        <button class="kp-editor-remove" onclick="removeSuggestionItem(${index})" title="删除">×</button>
        <input type="text" class="editor-input" placeholder="改进建议" value="${escapeHtml(suggestion || '')}"
               oninput="updateSuggestionField(${index}, this.value)">
    </div>`;
}

function updateRecordField(field, value) {
    if (!currentRecordData) return;
    currentRecordData[field] = value;
}

function updateQualityScore(val) {
    if (!currentRecordData) return;
    currentRecordData.quality_score = parseInt(val);
    document.getElementById('quality-score-display').textContent = val;
}

function setMastery(level) {
    if (!currentRecordData) return;
    currentRecordData.mastery_level = level;
    document.querySelectorAll('.mastery-option').forEach(el => {
        el.classList.toggle('active', el.textContent === level);
    });
}

function updateKpField(index, field, value) {
    if (!currentRecordData || !currentRecordData.knowledge_points) return;
    if (!currentRecordData.knowledge_points[index]) return;
    currentRecordData.knowledge_points[index][field] = value;
}

function addKpItem() {
    if (!currentRecordData) return;
    if (!currentRecordData.knowledge_points) currentRecordData.knowledge_points = [];
    currentRecordData.knowledge_points.push({ name: '', type: '概念', description: '' });
    renderRecordEditor(currentRecordData);
}

function removeKpItem(index) {
    if (!currentRecordData || !currentRecordData.knowledge_points) return;
    currentRecordData.knowledge_points.splice(index, 1);
    renderRecordEditor(currentRecordData);
}

function addTag() {
    if (!currentRecordData) return;
    const input = document.getElementById('new-tag-input');
    const tag = input.value.trim();
    if (!tag) return;
    if (!currentRecordData.tags) currentRecordData.tags = [];
    if (currentRecordData.tags.includes(tag)) {
        showToast('标签已存在', 'info');
        return;
    }
    currentRecordData.tags.push(tag);
    input.value = '';
    renderRecordEditor(currentRecordData);
}

function removeTag(index) {
    if (!currentRecordData || !currentRecordData.tags) return;
    currentRecordData.tags.splice(index, 1);
    renderRecordEditor(currentRecordData);
}

function addSuggestionItem() {
    if (!currentRecordData) return;
    if (!currentRecordData.improvement_suggestions) currentRecordData.improvement_suggestions = [];
    currentRecordData.improvement_suggestions.push('');
    renderRecordEditor(currentRecordData);
}

function removeSuggestionItem(index) {
    if (!currentRecordData || !currentRecordData.improvement_suggestions) return;
    currentRecordData.improvement_suggestions.splice(index, 1);
    renderRecordEditor(currentRecordData);
}

function updateSuggestionField(index, value) {
    if (!currentRecordData || !currentRecordData.improvement_suggestions) return;
    currentRecordData.improvement_suggestions[index] = value;
}

async function saveRecord() {
    if (!currentRecordData) {
        showToast('没有可保存的记录', 'error');
        return;
    }
    const btn = document.getElementById('btn-save-record');
    btn.textContent = '保存中...';
    btn.disabled = true;
    try {
        const res = await fetch('/api/daily-record/confirm', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(currentRecordData)
        });
        const data = await res.json();
        showToast(data.message || '保存成功', 'success');

        if (data.auto_tasks && data.auto_tasks.length > 0) {
            let taskMsg = `已自动生成 ${data.auto_tasks.length} 个复习任务：\n`;
            data.auto_tasks.forEach(t => { taskMsg += `• ${t.task} (截止: ${t.deadline})\n`; });
            setTimeout(() => showToast(taskMsg, 'info'), 500);
        }

        loadStats();
        loadTasks();

        // 保存成功后清空状态，开始新的学习记录
        resetRecordEditor();

    } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
    }
    btn.textContent = '💾 保存到数据库';
    btn.disabled = false;
}

function resetRecordEditor() {
    // 清空当前记录数据
    currentRecordData = null;
    recordChatHistory = [];

    // 重置对话区：只保留欢迎消息
    const chatBox = document.getElementById('record-chat-messages');
    chatBox.innerHTML = `
        <div class="record-msg assistant">
            <div class="record-msg-avatar">🤖</div>
            <div class="record-msg-bubble">
                你好！请告诉我今天学了什么，我来帮你分析和整理学习记录。
                <br><br>
                💡 <strong>使用提示：</strong>
                <br>• 直接描述学习内容，我会自动提取知识点
                <br>• 可以多轮对话，让我补充、修改、优化记录
                <br>• 右侧可以直接编辑结构化内容
                <br>• 满意后点击右上角"保存到数据库"
            </div>
        </div>
    `;

    // 重置右侧编辑器为空状态
    const editorBody = document.getElementById('record-editor-body');
    editorBody.innerHTML = `
        <div class="empty" style="padding: 40px 20px;">
            <div class="icon">📝</div>
            <p>在左侧发送学习内容<br>这里将显示结构化分析结果</p>
        </div>
    `;

    // 隐藏保存按钮
    document.getElementById('btn-save-record').style.display = 'none';
}

/* ========== 学习记录（旧的函数，保留兼容） ========== */
let pendingRecord = null;

async function analyzeRecord() {
    const content = document.getElementById('record-content').value.trim();
    if (!content) { showToast('请输入学习内容', 'error'); return; }
    const btn = document.getElementById('btn-analyze');
    btn.textContent = '分析中...'; btn.disabled = true;
    const preview = document.getElementById('record-preview');
    const analysis = document.getElementById('record-analysis');
    preview.style.display = 'block';
    analysis.innerHTML = `<div class="plan-loading"><div class="spinner"></div><p style="margin-top:12px;">正在分析学习内容...</p></div>`;

    try {
        const res = await fetch('/api/daily-record', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content })
        });
        if (!res.ok) {
            const err = await res.json();
            showToast(err.error || '分析失败', 'error');
            return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';
        let finalData = null;
        let streamBubble = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.type === 'text') {
                        if (!streamBubble) {
                            analysis.innerHTML = `
                                <div class="record-preview">
                                    <h4>📊 分析中...</h4>
                                    <div id="stream-text" style="white-space:pre-wrap;font-family:monospace;font-size:13px;background:#f8f9fa;padding:12px;border-radius:8px;color:#555;max-height:300px;overflow-y:auto;"></div>
                                </div>`;
                            streamBubble = document.getElementById('stream-text');
                        }
                        fullText += data.content;
                        streamBubble.textContent = fullText;
                        streamBubble.scrollTop = streamBubble.scrollHeight;
                    } else if (data.type === 'done') {
                        finalData = data.data;
                    }
                } catch (e) { }
            }
        }

        if (finalData) {
            pendingRecord = finalData;
            renderAnalysisResult(finalData);
        } else {
            showToast('分析失败', 'error');
        }
    } catch (e) { showToast('分析失败: ' + e.message, 'error'); }
    finally { btn.textContent = '分析并记录'; btn.disabled = false; }
}

function renderAnalysisResult(data) {
    const analysis = document.getElementById('record-analysis');
    let html = `<div class="record-preview">
        <h4>核心要点</h4><p>${data.summary || '无'}</p>
        <h4>质量评分</h4><p>${data.quality_score || 0} 分 ${data.quality_comment ? '- ' + data.quality_comment : ''}</p>`;
    
    if (data.correct_points && data.correct_points.length > 0) {
        html += `<h4 style="color:#22c55e;">✅ 理解正确的点</h4><ul class="kp-list">`;
        data.correct_points.forEach(cp => {
            html += `<li style="background:rgba(34,197,94,0.08);padding:8px 12px;border-radius:6px;border-left:3px solid #22c55e;">${cp}</li>`;
        });
        html += `</ul>`;
    }
    if (data.mistakes && data.mistakes.length > 0) {
        html += `<h4 style="color:#ef4444;">❌ 错误/待改进</h4><ul class="kp-list">`;
        data.mistakes.forEach(m => {
            html += `<li style="background:rgba(239,68,68,0.08);padding:8px 12px;border-radius:6px;border-left:3px solid #ef4444;">
                <div><strong>错误：</strong>${m.content || m}</div>
                ${m.explanation ? `<div style="margin-top:6px;padding-top:6px;border-top:1px dashed rgba(239,68,68,0.3);color:var(--text2);font-size:12px;"><strong style="color:var(--accent2);">💡 正确理解：</strong>${m.explanation}</div>` : ''}
            </li>`;
        });
        html += `</ul>`;
    }
    
    if (data.knowledge_points && data.knowledge_points.length) {
        html += `<h4>知识点</h4><ul class="kp-list">`;
        data.knowledge_points.forEach(kp => {
            html += `<li><strong>[${kp.type}] ${kp.name}</strong>: ${kp.description || ''}</li>`;
        });
        html += `</ul>`;
    }
    if (data.improvement_suggestions && data.improvement_suggestions.length) {
        html += `<h4>改进建议</h4><ul class="kp-list">`;
        data.improvement_suggestions.forEach(s => {
            html += `<li>${s}</li>`;
        });
        html += `</ul>`;
    }
    if (data.tags && data.tags.length) {
        html += `<h4>标签</h4><p>${data.tags.join(', ')}</p>`;
    }
    html += `<h4>掌握程度</h4>
        <div style="display:flex;gap:8px;margin-top:6px;">
            <label style="cursor:pointer;padding:6px 14px;border-radius:8px;border:1px solid var(--border);font-size:13px;transition:var(--transition);" class="mastery-opt" onclick="selectMastery(this,'生疏')">
                <input type="radio" name="mastery" value="生疏" ${data.mastery_level === '生疏' ? 'checked' : ''} style="display:none">生疏</label>
            <label style="cursor:pointer;padding:6px 14px;border-radius:8px;border:1px solid var(--border);font-size:13px;transition:var(--transition);" class="mastery-opt" onclick="selectMastery(this,'一般')">
                <input type="radio" name="mastery" value="一般" ${data.mastery_level === '一般' ? 'checked' : ''} style="display:none">一般</label>
            <label style="cursor:pointer;padding:6px 14px;border-radius:8px;border:1px solid var(--border);font-size:13px;transition:var(--transition);" class="mastery-opt" onclick="selectMastery(this,'熟悉')">
                <input type="radio" name="mastery" value="熟悉" ${data.mastery_level === '熟悉' ? 'checked' : ''} style="display:none">熟悉</label>
            <label style="cursor:pointer;padding:6px 14px;border-radius:8px;border:1px solid var(--border);font-size:13px;transition:var(--transition);" class="mastery-opt" onclick="selectMastery(this,'精通')">
                <input type="radio" name="mastery" value="精通" ${data.mastery_level === '精通' ? 'checked' : ''} style="display:none">精通</label>
        </div>`;
    html += `</div>`;
    analysis.innerHTML = html;
    // 高亮当前选中的掌握程度
    if (pendingRecord && pendingRecord.mastery_level) {
        document.querySelectorAll('.mastery-opt').forEach(el => {
            if (el.querySelector('input').value === pendingRecord.mastery_level) {
                el.style.borderColor = 'var(--accent)';
                el.style.background = 'var(--accent-light)';
                el.style.color = 'var(--accent2)';
                el.style.fontWeight = '600';
            }
        });
    }
}

function selectMastery(el, level) {
    if (pendingRecord) pendingRecord.mastery_level = level;
    document.querySelectorAll('.mastery-opt').forEach(opt => {
        opt.style.borderColor = 'var(--border)';
        opt.style.background = 'transparent';
        opt.style.color = 'var(--text)';
        opt.style.fontWeight = '400';
    });
    el.style.borderColor = 'var(--accent)';
    el.style.background = 'var(--accent-light)';
    el.style.color = 'var(--accent2)';
    el.style.fontWeight = '600';
    el.querySelector('input').checked = true;
}

async function confirmRecord() {
    if (!pendingRecord) return;
    try {
        const res = await fetch('/api/daily-record/confirm', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(pendingRecord)
        });
        const data = await res.json();
        showToast(data.message, 'success');

        // 显示自动生成的复习任务
        if (data.auto_tasks && data.auto_tasks.length > 0) {
            let taskHtml = `<div style="margin-top:12px;padding:12px 16px;background:linear-gradient(135deg,#e8f5e9,#e3f2fd);border-radius:10px;border:1px solid #a5d6a7;">
                <div style="font-weight:600;color:#2e7d32;margin-bottom:8px;">✅ 已自动生成 ${data.auto_tasks.length} 个复习任务</div>
                <div style="font-size:13px;color:#424242;line-height:1.8;">`;
            data.auto_tasks.forEach(t => {
                taskHtml += `<div>📌 ${escapeHtml(t.task)} — 截止：${t.deadline}</div>`;
            });
            taskHtml += `</div></div>`;
            const preview = document.getElementById('record-preview');
            preview.insertAdjacentHTML('beforeend', taskHtml);
            // 2秒后再关闭
            setTimeout(() => {
                preview.style.display = 'none';
                document.getElementById('record-content').value = '';
                pendingRecord = null;
                loadStats();
                loadTasks();
            }, 2500);
        } else {
            document.getElementById('record-preview').style.display = 'none';
            document.getElementById('record-content').value = '';
            pendingRecord = null;
            loadStats();
        }
    } catch (e) { showToast('保存失败', 'error'); }
}

function cancelRecord() {
    document.getElementById('record-preview').style.display = 'none';
    pendingRecord = null;
}

/* ========== 复习计划 ========== */
async function generatePlan() {
    const el = document.getElementById('plan-content');
    el.innerHTML = `<div class="plan-loading"><div class="spinner"></div><p style="margin-top:12px;">正在生成复习计划...</p></div>`;
    try {
        const res = await fetch('/api/review-plan', { method: 'POST' });
        const data = await res.json();
        if (data.error) {
            el.innerHTML = `<p style="color:var(--red)">${data.error}</p>`;
            return;
        }
        planData = data;
        planExpandedTaskKey = null;
        planKnowledgePoints = {};
        renderPlanPage(data);
    } catch (e) { el.innerHTML = `<p style="color:var(--red)">请求失败: ${e}</p>`; }
}

function renderPlanPage(data) {
    const el = document.getElementById('plan-content');
    const todayCount = data.today_tasks.length;
    const weekCount = data.week_tasks.length;

    let html = `
    <div class="plan-stats">
        <div class="plan-stat-card">
            <div class="plan-stat-num">${todayCount}</div>
            <div class="plan-stat-label">今日待复习</div>
        </div>
        <div class="plan-stat-card">
            <div class="plan-stat-num">${weekCount}</div>
            <div class="plan-stat-label">本周待复习</div>
        </div>
        <div class="plan-stat-card">
            <div class="plan-stat-num">${data.today_hours}h</div>
            <div class="plan-stat-label">今日预计时长</div>
        </div>
        <div class="plan-stat-card">
            <div class="plan-stat-num">${data.total_records}</div>
            <div class="plan-stat-label">学习记录</div>
        </div>
    </div>

    <div class="plan-section">
        <h3>📈 艾宾浩斯遗忘曲线</h3>
        <div class="curve-container">
            <canvas id="forgetting-curve" width="700" height="260"></canvas>
            <div class="curve-legend">
                <div class="legend-item"><span class="legend-dot" style="background:#4ecdc4"></span>记忆保留率</div>
                <div class="legend-item"><span class="legend-dot" style="background:#ff6b6b"></span>最佳复习节点</div>
            </div>
        </div>
        <div class="review-nodes">
            ${data.forgetting_curve.review_nodes.map(n => `
                <div class="review-node-card">
                    <div class="node-day">第${n.day}天</div>
                    <div class="node-label">${n.label}</div>
                    <div class="node-tip">${n.tip}</div>
                </div>
            `).join('')}
        </div>
    </div>

    <div class="plan-section">
        <h3>🔥 今日必复习 (${todayCount})</h3>
        ${todayCount === 0 ? '<div class="empty-tip">今天没有需要紧急复习的任务 🎉</div>' :
            data.today_tasks.map((t, i) => renderTaskCard(t, 'urgent_' + i, 'urgent')).join('')
        }
    </div>

    <div class="plan-section">
        <h3>📅 本周待复习 (${weekCount})</h3>
        ${weekCount === 0 ? '<div class="empty-tip">本周暂无待复习任务</div>' :
            data.week_tasks.map((t, i) => renderTaskCard(t, 'week_' + i, 'week')).join('')
        }
    </div>

    <div class="plan-section">
        <h3>📖 学习记录复习状态</h3>
        <div class="records-status">
            ${data.record_review_status.map(r => `
                <div class="record-status-item ${r.is_due_today ? 'due' : ''}">
                    <div class="record-date">${r.date} <span class="days-since">(${r.days_since}天前)</span></div>
                    <div class="record-kps">${r.knowledge_points.join(' · ') || '暂无知识点'}</div>
                    <div class="record-next">下次复习：第${r.next_review_day || '15+'}天 ${r.is_due_today ? '🔴 今天该复习了!' : ''}</div>
                </div>
            `).join('')}
        </div>
    </div>
    `;

    el.innerHTML = html;

    // 画遗忘曲线图
    setTimeout(() => drawForgettingCurve(data.forgetting_curve), 50);
}

function renderTaskCard(task, key, type) {
    const masteryColor = {
        '生疏': '#e74c3c', '一般': '#f39c12', '熟悉': '#27ae60', '精通': '#3498db'
    }[task.mastery] || '#999';
    const borderColor = type === 'urgent' ? '#ff6b6b' : (type === 'week' ? '#4ecdc4' : '#bdc3c7');
    const isExpanded = planExpandedTaskKey === key;
    const kpData = planKnowledgePoints[key];

    let detailHtml = '';
    if (isExpanded) {
        let kpHtml = '';
        if (!kpData || kpData.loading) {
            kpHtml = `<div class="kp-loading">⏳ 加载知识点中...</div>`;
        } else {
            const kpList = kpData.kps || [];
            const source = kpData.source || 'matched';
            if (kpList.length === 0) {
                kpHtml = `<div class="kp-loading" style="color: var(--text2);">暂无相关知识点</div>`;
            } else {
                kpHtml = `<div class="kp-list">
                    ${kpList.slice(0, 6).map((kp, ki) => `
                        <div class="kp-list-item">
                            <div class="kp-list-info">
                                <div class="kp-list-name">
                                    <span class="kp-list-type">${kp.type || '知识点'}</span>
                                    ${escapeHtml(kp.name)}
                                    <span class="kp-source-tag ${source}">${source === 'linked' ? '强关联' : '智能匹配'}</span>
                                </div>
                                <div class="kp-list-desc">${escapeHtml(kp.description || '')}</div>
                            </div>
                            <div style="display: flex; gap: 6px; align-items: center;">
                                <button class="kp-explain-btn" onclick="explainPlanKp('${key}', ${ki}, event)">讲解</button>
                                <button class="kp-quiz-btn" onclick="quizPlanSingleKp('${key}', ${ki}, event)">考察</button>
                            </div>
                        </div>
                    `).join('')}
                </div>`;
            }
        }

        detailHtml = `
        <div class="task-detail">
            <div class="task-detail-section">
                <div class="task-detail-title">📋 任务信息</div>
                <div class="task-detail-grid">
                    <div><span class="task-detail-label">分类</span><span>${task.category}</span></div>
                    <div><span class="task-detail-label">掌握程度</span><span>${task.mastery}</span></div>
                    <div><span class="task-detail-label">截止日期</span><span>${task.deadline}</span></div>
                    <div><span class="task-detail-label">优先级</span><span>${task.priority}</span></div>
                    <div><span class="task-detail-label">已复习</span><span>${task.review_count} 次</span></div>
                    <div><span class="task-detail-label">预估时长</span><span>${task.estimated_hours} 小时</span></div>
                </div>
            </div>
            <div class="task-detail-section">
                <div class="task-detail-title">📚 相关知识点</div>
                ${kpHtml}
            </div>
            <div class="task-detail-actions">
                <button class="btn btn-primary" onclick="startQuizFromPlan('${key}')">🎯 开始考察这个任务</button>
                <button class="btn btn-success" onclick="markPlanTaskReviewed('${key}')">✅ 标记已复习</button>
            </div>
        </div>`;
    }

    return `
    <div class="plan-task-card ${isExpanded ? 'expanded' : ''}" style="border-left:4px solid ${borderColor};">
        <div class="task-header" onclick="togglePlanTaskDetail('${key}')">
            <span class="task-name">${escapeHtml(task.name)}</span>
            <div style="display:flex;align-items:center;gap:12px;">
                <span class="task-priority">优先级 ${task.priority}</span>
                <span class="task-expand-icon">${isExpanded ? '▲' : '▼'}</span>
            </div>
        </div>
        <div class="task-meta">
            <span class="task-tag">${task.category}</span>
            <span class="task-mastery" style="color:${masteryColor}">${task.mastery}</span>
            <span class="task-deadline">📅 ${task.deadline}</span>
            <span class="task-hours">⏱ ${task.estimated_hours}h</span>
            <span class="task-reviews">🔄 复习${task.review_count}次</span>
        </div>
        ${detailHtml}
    </div>`;
}

function getPlanTaskByKey(key) {
    if (!planData) return null;
    const [type, idxStr] = key.split('_');
    const idx = parseInt(idxStr);
    if (type === 'urgent' && planData.today_tasks[idx]) {
        return planData.today_tasks[idx];
    } else if (type === 'week' && planData.week_tasks[idx]) {
        return planData.week_tasks[idx];
    }
    return null;
}

function togglePlanTaskDetail(key) {
    if (planExpandedTaskKey === key) {
        planExpandedTaskKey = null;
    } else {
        planExpandedTaskKey = key;
        loadPlanTaskKnowledgePoints(key);
    }
    if (planData) renderPlanPage(planData);
}

async function loadPlanTaskKnowledgePoints(key) {
    if (planKnowledgePoints[key]) return;
    planKnowledgePoints[key] = { loading: true };
    const task = getPlanTaskByKey(key);
    if (!task || task.task_index === undefined) {
        planKnowledgePoints[key] = { kps: [], source: 'matched' };
        if (planExpandedTaskKey === key && planData) renderPlanPage(planData);
        return;
    }
    try {
        const res = await fetch(`/api/task/${task.task_index}/knowledge-points`);
        const data = await res.json();
        if (data.knowledge_points) {
            planKnowledgePoints[key] = {
                kps: data.knowledge_points,
                source: data.source || 'matched'
            };
            if (planExpandedTaskKey === key && planData) {
                renderPlanPage(planData);
            }
        }
    } catch (e) {
        console.error('加载知识点失败:', e);
        planKnowledgePoints[key] = { kps: [], source: 'matched' };
    }
}

function explainPlanKp(key, kpIdx, event) {
    if (event) event.stopPropagation();
    const kpData = planKnowledgePoints[key];
    if (!kpData || !kpData.kps || !kpData.kps[kpIdx]) return;
    const kp = kpData.kps[kpIdx];
    openKpExplain(kp);
}

async function quizPlanSingleKp(key, kpIdx, event) {
    if (event) event.stopPropagation();
    const kpData = planKnowledgePoints[key];
    if (!kpData || !kpData.kps || !kpData.kps[kpIdx]) return;
    const kp = kpData.kps[kpIdx];

    currentQuizParams = { knowledge_points: [kp], title: kp.name };
    switchPage('quiz');
    const container = document.getElementById('quiz-container');
    container.innerHTML = `<div class="plan-loading"><div class="spinner"></div><p style="margin-top:12px;">正在为「${escapeHtml(kp.name)}」出题...</p></div>`;

    try {
        const res = await fetch('/api/quiz/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(currentQuizParams)
        });
        if (!res.ok) {
            const err = await res.json();
            container.innerHTML = `<p style="color:var(--red)">${err.error || '请求失败'}</p>`;
            return;
        }
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';
        let finalData = null;
        let bubble = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.type === 'text') {
                        if (!bubble) {
                            container.innerHTML = '';
                            const div = document.createElement('div');
                            div.className = 'quiz-bubble';
                            div.id = 'quiz-bubble';
                            container.appendChild(div);
                            bubble = div;
                        }
                        fullText += data.content;
                        bubble.textContent = fullText;
                        container.scrollTop = container.scrollHeight;
                    } else if (data.type === 'done') {
                        finalData = data;
                    }
                } catch (e) { }
            }
        }

        if (finalData) {
            renderQuizQuestionWithInput(finalData.question);
        } else if (!fullText) {
            container.innerHTML = `<p style="color:var(--red)">出题失败</p>`;
        }
    } catch (e) {
        container.innerHTML = `<p style="color:var(--red)">请求失败: ${e.message}</p>`;
    }
}

async function startQuizFromPlan(key) {
    const task = getPlanTaskByKey(key);
    if (!task) return;
    currentQuizParams = { task_id: task.task_id, task_index: task.task_index, title: task.name, source_page: 'review-plan', plan_key: key };
    switchPage('quiz');
    const container = document.getElementById('quiz-container');
    container.innerHTML = `<div class="plan-loading"><div class="spinner"></div><p style="margin-top:12px;">正在为「${escapeHtml(task.name)}」出题...</p></div>`;

    try {
        const res = await fetch('/api/quiz/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(currentQuizParams)
        });
        if (!res.ok) {
            const err = await res.json();
            container.innerHTML = `<p style="color:var(--red)">${err.error || '请求失败'}</p>`;
            return;
        }
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';
        let finalData = null;
        let bubble = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.type === 'text') {
                        if (!bubble) {
                            container.innerHTML = '';
                            const div = document.createElement('div');
                            div.className = 'quiz-bubble';
                            div.id = 'quiz-bubble';
                            container.appendChild(div);
                            bubble = div;
                        }
                        fullText += data.content;
                        bubble.textContent = fullText;
                        container.scrollTop = container.scrollHeight;
                    } else if (data.type === 'done') {
                        finalData = data;
                    }
                } catch (e) { }
            }
        }

        if (finalData) {
            renderQuizQuestionWithInput(finalData.question);
        } else if (!fullText) {
            container.innerHTML = `<p style="color:var(--red)">出题失败</p>`;
        }
    } catch (e) {
        container.innerHTML = `<p style="color:var(--red)">请求失败: ${e.message}</p>`;
    }
}

async function markPlanTaskReviewed(key) {
    const task = getPlanTaskByKey(key);
    if (!task || task.task_index === undefined) return;
    try {
        const res = await fetch(`/api/tasks/${task.task_index}/review`, { method: 'POST' });
        const data = await res.json();
        showToast(data.message, 'success');
        loadStats();
        if (planData) {
            task.review_count = (task.review_count || 0) + 1;
            renderPlanPage(planData);
        }
    } catch (e) { showToast('操作失败', 'error'); }
}

function drawForgettingCurve(curveData) {
    const canvas = document.getElementById('forgetting-curve');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;
    const padding = { top: 30, right: 20, bottom: 40, left: 50 };
    const chartW = W - padding.left - padding.right;
    const chartH = H - padding.top - padding.bottom;

    ctx.clearRect(0, 0, W, H);

    // 数据点（使用天作为单位的平滑版本）
    const dayLabels = [0, 0.014, 0.04, 0.38, 1, 2, 6, 31];
    const retention = [100, 58.2, 44.2, 35.8, 33.7, 27.8, 25.4, 21.1];

    // 绘制网格
    ctx.strokeStyle = '#e8f5e9';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 5; i++) {
        const y = padding.top + (chartH / 5) * i;
        ctx.beginPath();
        ctx.moveTo(padding.left, y);
        ctx.lineTo(W - padding.right, y);
        ctx.stroke();
        // Y轴刻度
        ctx.fillStyle = '#7f8c8d';
        ctx.font = '11px sans-serif';
        ctx.textAlign = 'right';
        ctx.fillText(100 - i * 20 + '%', padding.left - 8, y + 4);
    }

    // 绘制X轴标签
    ctx.fillStyle = '#7f8c8d';
    ctx.font = '11px sans-serif';
    ctx.textAlign = 'center';
    const xLabels = ['0天', '1天', '2天', '3天', '4天', '5天', '6天', '7天', '15天', '31天'];
    const xPositions = [0, 1, 2, 3, 4, 5, 6, 7, 15, 31];
    xPositions.forEach((pos, i) => {
        const x = padding.left + (pos / 31) * chartW;
        ctx.fillText(xLabels[i], x, H - padding.bottom + 20);
    });

    // 绘制曲线（使用对数缩放让曲线更明显）
    function getX(day) {
        return padding.left + (Math.log(day + 1) / Math.log(32)) * chartW;
    }
    function getY(val) {
        return padding.top + (1 - val / 100) * chartH;
    }

    // 渐变填充
    const grad = ctx.createLinearGradient(0, padding.top, 0, H - padding.bottom);
    grad.addColorStop(0, 'rgba(78, 205, 196, 0.3)');
    grad.addColorStop(1, 'rgba(78, 205, 196, 0.02)');

    // 绘制平滑曲线
    ctx.beginPath();
    ctx.moveTo(getX(0), getY(100));
    // 用更多的点做平滑曲线
    const smoothPoints = [];
    for (let day = 0; day <= 31; day += 0.5) {
        // 艾宾浩斯公式近似: R = e^(-t/S)
        // 用插值让曲线更符合真实数据
        let r;
        if (day <= 0.014) r = 100 - (100 - 58.2) * (day / 0.014);
        else if (day <= 0.04) r = 58.2 - (58.2 - 44.2) * ((day - 0.014) / 0.026);
        else if (day <= 0.38) r = 44.2 - (44.2 - 35.8) * ((day - 0.04) / 0.34);
        else if (day <= 1) r = 35.8 - (35.8 - 33.7) * ((day - 0.38) / 0.62);
        else if (day <= 2) r = 33.7 - (33.7 - 27.8) * ((day - 1) / 1);
        else if (day <= 6) r = 27.8 - (27.8 - 25.4) * ((day - 2) / 4);
        else r = 25.4 - (25.4 - 21.1) * ((day - 6) / 25);
        smoothPoints.push({ x: getX(day), y: getY(r) });
    }
    for (let i = 0; i < smoothPoints.length; i++) {
        ctx.lineTo(smoothPoints[i].x, smoothPoints[i].y);
    }
    ctx.lineTo(getX(31), getY(0));
    ctx.lineTo(getX(0), getY(0));
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // 绘制曲线描边
    ctx.beginPath();
    for (let i = 0; i < smoothPoints.length; i++) {
        if (i === 0) ctx.moveTo(smoothPoints[i].x, smoothPoints[i].y);
        else ctx.lineTo(smoothPoints[i].x, smoothPoints[i].y);
    }
    ctx.strokeStyle = '#4ecdc4';
    ctx.lineWidth = 2.5;
    ctx.stroke();

    // 标注复习节点
    const reviewDays = [0, 1, 2, 4, 7, 15];
    const nodeColors = ['#2ecc71', '#ff6b6b', '#ff8e53', '#ffd93d', '#6c5ce7', '#3498db'];
    reviewDays.forEach((day, i) => {
        // 计算该天的保留率
        let r;
        if (day === 0) r = 100;
        else if (day === 1) r = 33.7;
        else if (day === 2) r = 27.8;
        else if (day === 4) r = 26;
        else if (day === 7) r = 25;
        else if (day === 15) r = 23;
        else r = 21;

        const x = getX(day);
        const y = getY(r);

        // 绘制复习节点标记
        ctx.beginPath();
        ctx.arc(x, y, 6, 0, Math.PI * 2);
        ctx.fillStyle = nodeColors[i % nodeColors.length];
        ctx.fill();
        ctx.strokeStyle = '#fff';
        ctx.lineWidth = 2;
        ctx.stroke();

        // 垂直虚线
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(x, H - padding.bottom);
        ctx.strokeStyle = nodeColors[i % nodeColors.length] + '66';
        ctx.lineWidth = 1;
        ctx.stroke();
        ctx.setLineDash([]);
    });

    // Y轴标题
    ctx.save();
    ctx.translate(14, H / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillStyle = '#95a5a6';
    ctx.font = '12px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('记忆保留率 (%)', 0, 0);
    ctx.restore();
}

function formatPlanContent(text) {
    return escapeHtml(text)
        .replace(/【([^】]+)】/g, '<strong style="color:var(--accent2);font-size:15px;">【$1】</strong>');
}

/* ========== 对话 ========== */
let chatSending = false;

function addMsg(role, text) {
    const box = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.className = `msg ${role}`;
    div.innerHTML = `<div class="msg-avatar">${role === 'user' ? '😊' : '🤖'}</div><div class="msg-bubble">${escapeHtml(text)}</div>`;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
}

function addToolMsg(text) {
    const box = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.className = 'msg-tool';
    div.textContent = text;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
}

function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
}

async function sendChat() {
    if (chatSending) return;
    const input = document.getElementById('chat-input');
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    addMsg('user', text);
    chatSending = true;

    try {
        const res = await fetch('/api/chat', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt: text, stream: true })
        });
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let assistantText = '';
        let bubble = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.type === 'text') {
                        if (!bubble) {
                            const box = document.getElementById('chat-messages');
                            const div = document.createElement('div');
                            div.className = 'msg assistant';
                            div.innerHTML = `<div class="msg-avatar">🤖</div><div class="msg-bubble"></div>`;
                            box.appendChild(div);
                            bubble = div.querySelector('.msg-bubble');
                        }
                        assistantText += data.content;
                        bubble.textContent = assistantText;
                        document.getElementById('chat-messages').scrollTop =
                            document.getElementById('chat-messages').scrollHeight;
                    } else if (data.type === 'tool_call') {
                        addToolMsg(`[调用工具: ${data.name}]`);
                    } else if (data.type === 'tool_result') {
                        addToolMsg(`[工具结果: ${data.result}]`);
                    }
                } catch (e) { }
            }
        }
        if (!assistantText) addMsg('assistant', '(无回复)');
    } catch (e) {
        addMsg('assistant', '请求失败: ' + e.message);
    }
    chatSending = false;
    loadStats();
}

/* ========== 考察模式 ========== */
async function startQuiz() {
    const container = document.getElementById('quiz-container');
    container.innerHTML = `<div class="plan-loading"><div class="spinner"></div><p style="margin-top:12px;">正在出题...</p></div>`;
    try {
        const fetchOpts = { method: 'POST' };
        if (currentQuizParams) {
            fetchOpts.headers = { 'Content-Type': 'application/json' };
            fetchOpts.body = JSON.stringify(currentQuizParams);
        }
        const res = await fetch('/api/quiz/start', fetchOpts);
        if (!res.ok) {
            const err = await res.json();
            container.innerHTML = `<p style="color:var(--red)">${err.error || '请求失败'}</p>`;
            return;
        }
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';
        let finalData = null;
        let bubble = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.type === 'text') {
                        if (!bubble) {
                            container.innerHTML = '';
                            const div = document.createElement('div');
                            div.className = 'quiz-bubble';
                            div.id = 'quiz-bubble';
                            container.appendChild(div);
                            bubble = div;
                        }
                        fullText += data.content;
                        bubble.textContent = fullText;
                        container.scrollTop = container.scrollHeight;
                    } else if (data.type === 'done') {
                        finalData = data;
                    }
                } catch (e) { }
            }
        }

        if (finalData) {
            renderQuizQuestionWithInput(finalData.question);
        } else if (!fullText) {
            container.innerHTML = `<p style="color:var(--red)">出题失败</p>`;
        }
    } catch (e) { container.innerHTML = `<p style="color:var(--red)">请求失败: ${e.message}</p>`; }
}

function renderQuizQuestionWithInput(question) {
    const container = document.getElementById('quiz-container');
    container.innerHTML = `
        <div class="quiz-bubble">${escapeHtml(question)}</div>
        <div class="quiz-input">
            <textarea id="quiz-answer" placeholder="输入你的答案..." onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();submitQuizAnswer();}"></textarea>
            <div style="display:flex;flex-direction:column;gap:8px;">
                <button class="btn btn-primary" onclick="submitQuizAnswer()">提交答案</button>
                <button class="btn btn-danger btn-sm" onclick="endQuiz()">结束考察</button>
            </div>
        </div>`;
    const ta = document.getElementById('quiz-answer');
    if (ta) ta.focus();
}

function renderQuizQuestion(question) {
    renderQuizQuestionWithInput(question);
}

async function submitQuizAnswer() {
    const answer = document.getElementById('quiz-answer').value.trim();
    if (!answer) return;
    const container = document.getElementById('quiz-container');
    container.innerHTML = container.innerHTML.replace(/<div class="quiz-input">[\s\S]*<\/div>/, '') +
        `<div class="msg user" style="max-width:75%;margin-left:auto;margin-bottom:16px;display:flex;gap:10px;flex-direction:row-reverse;">
            <div class="msg-avatar" style="width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,var(--accent),#6c5ce7);color:#fff;font-size:16px;">😊</div>
            <div class="msg-bubble" style="padding:10px 16px;border-radius:16px;background:linear-gradient(135deg,var(--accent),#6c5ce7);color:#fff;white-space:pre-wrap;">${escapeHtml(answer)}</div>
        </div>
        <div class="plan-loading"><div class="spinner"></div><p style="margin-top:12px;">老师正在批改...</p></div>`;
    try {
        const res = await fetch('/api/quiz/answer', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ answer })
        });
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';
        let finalData = null;
        let resultBubble = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.type === 'text') {
                        if (!resultBubble) {
                            const loading = container.querySelector('.plan-loading');
                            if (loading) loading.remove();
                            resultBubble = document.createElement('div');
                            resultBubble.className = 'quiz-result';
                            resultBubble.id = 'quiz-result-stream';
                            container.appendChild(resultBubble);
                        }
                        fullText += data.content;
                        resultBubble.textContent = fullText;
                        container.scrollTop = container.scrollHeight;
                    } else if (data.type === 'done') {
                        finalData = data;
                    }
                } catch (e) { }
            }
        }

        if (finalData) {
            if (finalData.ended) {
                const backBtn = currentQuizParams && currentQuizParams.source_page
                    ? `<button class="btn btn-secondary" onclick="backToTaskFromQuiz()" style="margin-right:8px;">← 返回任务</button>`
                    : '';
                const statsHtml = buildQuizStatsHtml(finalData.stats, finalData.mastery_update);
                container.innerHTML = `${statsHtml}
                    <div class="quiz-bubble">${escapeHtml(finalData.reply)}</div>
                    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;">
                        ${backBtn}
                        <button class="btn btn-primary" onclick="startQuiz()">再来一轮</button>
                    </div>`;
            } else {
                const resultHtml = `<div class="quiz-result">${escapeHtml(finalData.result)}</div>`;
                const nextBtn = finalData.has_next
                    ? `<button class="btn btn-primary" onclick="showNextQuestion('${encodeURIComponent(finalData.next_question)}')" style="margin-top:12px;">下一题 →</button>`
                    : `<button class="btn btn-primary" onclick="startQuiz()" style="margin-top:12px;">再来一轮</button>`;
                container.innerHTML = resultHtml + nextBtn;
            }
        }
    } catch (e) { container.innerHTML = `<p style="color:var(--red)">请求失败: ${e.message}</p>`; }
}

function showNextQuestion(encodedQ) {
    const question = decodeURIComponent(encodedQ);
    renderQuizQuestion(question);
}

function buildQuizStatsHtml(stats, masteryUpdate) {
    if (!stats || stats.total === 0) return '';

    const rate = Math.round((stats.correct_rate || 0) * 100);
    let rateColor = 'var(--red)';
    if (rate >= 85) rateColor = 'var(--green)';
    else if (rate >= 50) rateColor = 'var(--accent)';

    let masteryHtml = '';
    if (masteryUpdate) {
        const changed = masteryUpdate.mastery_changed;
        const arrow = changed
            ? (masteryUpdate.new_mastery === '精通' || masteryUpdate.old_mastery === '生疏' ? '→' : masteryUpdate.new_mastery > masteryUpdate.old_mastery ? '↑' : '↓')
            : '→';
        const changeColor = changed
            ? (masteryUpdate.new_mastery > masteryUpdate.old_mastery ? 'var(--green)' : 'var(--red)')
            : 'var(--text-secondary)';
        masteryHtml = `
            <div style="margin-top:12px;padding-top:12px;border-top:1px solid var(--border);">
                <div style="font-weight:600;margin-bottom:8px;">📊 掌握程度变化</div>
                <div style="display:flex;align-items:center;gap:8px;">
                    <span>${masteryUpdate.old_mastery}</span>
                    <span style="color:${changeColor};font-weight:600;">${arrow}</span>
                    <span style="font-weight:600;color:${changeColor};">${masteryUpdate.new_mastery}</span>
                    <span style="margin-left:auto;color:var(--text-secondary);font-size:12px;">
                        已复习 ${masteryUpdate.new_review_count} 次
                    </span>
                </div>
            </div>
        `;
    }

    return `
        <div style="background:var(--bg-secondary);border-radius:12px;padding:16px;margin-bottom:16px;border:1px solid var(--border);">
            <div style="font-weight:600;margin-bottom:12px;">📝 本次考察统计</div>
            <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;text-align:center;">
                <div>
                    <div style="font-size:24px;font-weight:700;">${stats.total}</div>
                    <div style="font-size:12px;color:var(--text-secondary);">总题数</div>
                </div>
                <div>
                    <div style="font-size:24px;font-weight:700;color:var(--green);">${stats.correct}</div>
                    <div style="font-size:12px;color:var(--text-secondary);">正确</div>
                </div>
                <div>
                    <div style="font-size:24px;font-weight:700;color:var(--accent);">${stats.partial}</div>
                    <div style="font-size:12px;color:var(--text-secondary);">不完整</div>
                </div>
                <div>
                    <div style="font-size:24px;font-weight:700;color:var(--red);">${stats.wrong}</div>
                    <div style="font-size:12px;color:var(--text-secondary);">错误</div>
                </div>
            </div>
            <div style="margin-top:12px;">
                <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
                    <span style="font-size:13px;">正确率</span>
                    <span style="font-size:13px;font-weight:600;color:${rateColor};">${rate}%</span>
                </div>
                <div style="height:8px;background:var(--border);border-radius:4px;overflow:hidden;">
                    <div style="height:100%;width:${rate}%;background:${rateColor};border-radius:4px;transition:width .5s;"></div>
                </div>
            </div>
            ${masteryHtml}
        </div>
    `;
}

async function endQuiz() {
    const container = document.getElementById('quiz-container');
    container.innerHTML = `<div class="plan-loading"><div class="spinner"></div><p style="margin-top:12px;">正在生成总结...</p></div>`;
    try {
        const res = await fetch('/api/quiz/answer', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ answer: 'q' })
        });
        if (!res.ok) {
            const err = await res.json();
            container.innerHTML = `<p style="color:var(--red)">${err.error || '请求失败'}</p>`;
            return;
        }
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';
        let finalData = null;
        let resultBubble = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.type === 'text') {
                        if (!resultBubble) {
                            const loading = container.querySelector('.plan-loading');
                            if (loading) loading.remove();
                            resultBubble = document.createElement('div');
                            resultBubble.className = 'quiz-result';
                            container.appendChild(resultBubble);
                        }
                        fullText += data.content;
                        resultBubble.textContent = fullText;
                        container.scrollTop = container.scrollHeight;
                    } else if (data.type === 'done') {
                        finalData = data;
                    }
                } catch (e) { }
            }
        }

        if (finalData && finalData.ended) {
            const backBtn = currentQuizParams && currentQuizParams.source_page
                ? `<button class="btn btn-secondary" onclick="backToTaskFromQuiz()" style="margin-right:8px;">← 返回任务</button>`
                : '';
            const statsHtml = buildQuizStatsHtml(finalData.stats, finalData.mastery_update);
            container.innerHTML = `${statsHtml}
                <div class="quiz-result">${escapeHtml(finalData.reply)}</div>
                <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;">
                    ${backBtn}
                    <button class="btn btn-primary" onclick="startQuiz()">再来一轮</button>
                </div>`;
        } else if (fullText) {
            const backBtn = currentQuizParams && currentQuizParams.source_page
                ? `<button class="btn btn-secondary" onclick="backToTaskFromQuiz()" style="margin-right:8px;">← 返回任务</button>`
                : '';
            container.innerHTML = `<div class="quiz-result">${escapeHtml(fullText)}</div>
                <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:12px;">
                    ${backBtn}
                    <button class="btn btn-primary" onclick="startQuiz()">再来一轮</button>
                </div>`;
        } else {
            container.innerHTML = `<p style="color:var(--red)">生成总结失败</p>`;
        }
    } catch (e) { container.innerHTML = `<p style="color:var(--red)">请求失败: ${e.message}</p>`; }
}

/* ========== 知识点讲解 ========== */

function backToTaskFromQuiz() {
    if (!currentQuizParams) {
        switchPage('tasks');
        return;
    }
    const source = currentQuizParams.source_page;
    if (source === 'tasks') {
        switchPage('tasks');
    } else if (source === 'review-plan') {
        switchPage('review-plan');
    } else {
        switchPage('tasks');
    }
}

function explainKnowledgePoint(taskIdx, kpIdx) {
    const kpData = taskKnowledgePoints[taskIdx];
    if (!kpData || !kpData.kps || !kpData.kps[kpIdx]) return;
    const kp = kpData.kps[kpIdx];
    openKpExplain(kp);
}

async function quizSingleKnowledgePoint(taskIdx, kpIdx, event) {
    if (event) event.stopPropagation();
    const kpData = taskKnowledgePoints[taskIdx];
    if (!kpData || !kpData.kps || !kpData.kps[kpIdx]) return;
    const kp = kpData.kps[kpIdx];

    currentQuizParams = { knowledge_points: [kp], title: kp.name };
    switchPage('quiz');
    const container = document.getElementById('quiz-container');
    container.innerHTML = `<div class="plan-loading"><div class="spinner"></div><p style="margin-top:12px;">正在为「${escapeHtml(kp.name)}」出题...</p></div>`;

    try {
        const res = await fetch('/api/quiz/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(currentQuizParams)
        });
        if (!res.ok) {
            const err = await res.json();
            container.innerHTML = `<p style="color:var(--red)">${err.error || '请求失败'}</p>`;
            return;
        }
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';
        let finalData = null;
        let bubble = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');
            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const data = JSON.parse(line.slice(6));
                    if (data.type === 'text') {
                        if (!bubble) {
                            container.innerHTML = '';
                            const div = document.createElement('div');
                            div.className = 'quiz-bubble';
                            div.id = 'quiz-bubble';
                            container.appendChild(div);
                            bubble = div;
                        }
                        fullText += data.content;
                        bubble.textContent = fullText;
                        container.scrollTop = container.scrollHeight;
                    } else if (data.type === 'done') {
                        finalData = data;
                    }
                } catch (e) { }
            }
        }

        if (finalData) {
            renderQuizQuestionWithInput(finalData.question);
        } else if (!fullText) {
            container.innerHTML = `<p style="color:var(--red)">出题失败</p>`;
        }
    } catch (e) {
        container.innerHTML = `<p style="color:var(--red)">请求失败: ${e.message}</p>`;
    }
}

let kpExplainAbortController = null;

function openKpExplain(kp) {
    const modal = document.getElementById('kp-explain-modal');
    const title = document.getElementById('kp-explain-title');
    const content = document.getElementById('kp-explain-content');

    title.textContent = `📖 ${kp.name}`;
    content.textContent = '';
    modal.classList.add('show');

    // 流式获取讲解内容
    if (kpExplainAbortController) {
        kpExplainAbortController.abort();
    }
    kpExplainAbortController = new AbortController();

    fetch('/api/knowledge/explain', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            name: kp.name,
            type: kp.type,
            description: kp.description
        }),
        signal: kpExplainAbortController.signal
    }).then(res => {
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';

        function read() {
            reader.read().then(({ done, value }) => {
                if (done) return;
                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split('\n');
                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.type === 'text') {
                            fullText += data.content;
                            content.textContent = fullText;
                            // 滚动到底部
                            const modalBody = content.parentElement;
                            modalBody.scrollTop = modalBody.scrollHeight;
                        }
                    } catch (e) { }
                }
                read();
            }).catch(() => { });
        }
        read();
    }).catch(e => {
        if (e.name !== 'AbortError') {
            content.textContent = '讲解加载失败: ' + e.message;
        }
    });
}

function closeKpExplain() {
    const modal = document.getElementById('kp-explain-modal');
    modal.classList.remove('show');
    if (kpExplainAbortController) {
        kpExplainAbortController.abort();
        kpExplainAbortController = null;
    }
}

/* ========== 知识点关联 ========== */

async function openKpLinkModal(taskIdx, event) {
    if (event) event.stopPropagation();
    currentLinkTaskIndex = taskIdx;
    selectedKpIds.clear();

    // 标记当前已关联的知识点
    const kpData = taskKnowledgePoints[taskIdx];
    if (kpData && kpData.source === 'linked' && kpData.kps) {
        kpData.kps.forEach(kp => {
            if (kp.id) selectedKpIds.add(kp.id);
        });
    }

    const modal = document.getElementById('kp-link-modal');
    const searchInput = document.getElementById('kp-link-search-input');
    searchInput.value = '';
    modal.classList.add('show');

    // 加载所有知识点
    try {
        const res = await fetch('/api/knowledge/list');
        const data = await res.json();
        allKnowledgePoints = data.knowledge_points || [];
        renderKpLinkList('');
    } catch (e) {
        console.error('加载知识点列表失败:', e);
        document.getElementById('kp-link-list').innerHTML = '<p style="color:var(--red);text-align:center;">加载失败</p>';
    }
}

function closeKpLinkModal() {
    const modal = document.getElementById('kp-link-modal');
    modal.classList.remove('show');
    currentLinkTaskIndex = -1;
    allKnowledgePoints = [];
    selectedKpIds.clear();
}

function filterKpLinkList() {
    const keyword = document.getElementById('kp-link-search-input').value.trim().toLowerCase();
    renderKpLinkList(keyword);
}

function renderKpLinkList(keyword) {
    const container = document.getElementById('kp-link-list');
    let filtered = allKnowledgePoints;
    if (keyword) {
        filtered = allKnowledgePoints.filter(kp =>
            kp.name.toLowerCase().includes(keyword) ||
            (kp.description || '').toLowerCase().includes(keyword)
        );
    }

    if (filtered.length === 0) {
        container.innerHTML = '<p style="color:var(--text2);text-align:center;padding:20px;">暂无知识点</p>';
        return;
    }

    container.innerHTML = filtered.map(kp => {
        const isSelected = selectedKpIds.has(kp.id);
        return `
            <div class="kp-link-item ${isSelected ? 'selected' : ''}" onclick="toggleKpSelect(${kp.id})">
                <div class="kp-link-checkbox"></div>
                <div class="kp-link-info">
                    <div class="kp-link-name">${escapeHtml(kp.name)}</div>
                    <div class="kp-link-desc">
                        <span class="kp-link-type">${kp.type || '知识点'}</span>
                        ${escapeHtml(kp.description || '')}
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

function toggleKpSelect(kpId) {
    if (selectedKpIds.has(kpId)) {
        selectedKpIds.delete(kpId);
    } else {
        selectedKpIds.add(kpId);
    }
    const keyword = document.getElementById('kp-link-search-input').value.trim().toLowerCase();
    renderKpLinkList(keyword);
}

async function confirmKpLink() {
    if (currentLinkTaskIndex < 0) return;
    if (selectedKpIds.size === 0) {
        showToast('请至少选择一个知识点', 'error');
        return;
    }

    try {
        const res = await fetch(`/api/task/${currentLinkTaskIndex}/knowledge-link`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ knowledge_ids: Array.from(selectedKpIds) })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || '关联失败');

        showToast(data.message, 'success');
        closeKpLinkModal();
        // 重新加载任务知识点
        delete taskKnowledgePoints[currentLinkTaskIndex];
        loadTaskKnowledgePoints(currentLinkTaskIndex);
    } catch (e) {
        showToast('关联失败: ' + e.message, 'error');
    }
}

async function unlinkKnowledgePoint(taskIdx, kpIdx, event) {
    if (event) event.stopPropagation();
    const kpData = taskKnowledgePoints[taskIdx];
    if (!kpData || !kpData.kps || !kpData.kps[kpIdx]) return;
    const kp = kpData.kps[kpIdx];
    if (!kp.id) return;

    if (!confirm('确定要移除这个知识点的关联吗？')) return;

    try {
        const res = await fetch(`/api/task/${taskIdx}/knowledge-unlink`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ knowledge_id: kp.id })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || '移除失败');

        showToast(data.message, 'success');
        // 重新加载
        delete taskKnowledgePoints[taskIdx];
        loadTaskKnowledgePoints(taskIdx);
    } catch (e) {
        showToast('移除失败: ' + e.message, 'error');
    }
}

/* ========== 用户认证 ========== */
let authToken = localStorage.getItem('auth_token');
let currentUser = JSON.parse(localStorage.getItem('current_user') || 'null');

function getAuthHeaders() {
    const headers = { 'Content-Type': 'application/json' };
    if (authToken) {
        headers['Authorization'] = 'Bearer ' + authToken;
    }
    return headers;
}

function showAuthModal(mode, forceLogin = false) {
    const modal = document.getElementById('auth-modal');
    const title = document.getElementById('auth-title');
    const submitBtn = document.getElementById('auth-submit-btn');
    const switchText = document.getElementById('auth-switch-text');
    const switchLink = document.getElementById('auth-switch-link');
    const nicknameGroup = document.getElementById('nickname-group');
    const errorEl = document.getElementById('auth-error');
    const closeBtn = modal.querySelector('.auth-close');

    errorEl.style.display = 'none';
    document.getElementById('auth-username').value = '';
    document.getElementById('auth-password').value = '';
    document.getElementById('auth-nickname').value = '';

    if (forceLogin) {
        closeBtn.style.display = 'none';
        modal.dataset.forceLogin = 'true';
    } else {
        closeBtn.style.display = 'block';
        modal.dataset.forceLogin = 'false';
    }

    if (mode === 'login') {
        title.textContent = '登录';
        submitBtn.textContent = '登录';
        switchText.textContent = '还没有账号？';
        switchLink.textContent = '立即注册';
        nicknameGroup.style.display = 'none';
        modal.dataset.mode = 'login';
    } else {
        title.textContent = '注册';
        submitBtn.textContent = '注册';
        switchText.textContent = '已有账号？';
        switchLink.textContent = '立即登录';
        nicknameGroup.style.display = 'block';
        modal.dataset.mode = 'register';
    }
    modal.style.display = 'flex';
}

function hideAuthModal() {
    const modal = document.getElementById('auth-modal');
    if (modal.dataset.forceLogin === 'true') return;
    modal.style.display = 'none';
}

function switchAuthMode() {
    const modal = document.getElementById('auth-modal');
    const currentMode = modal.dataset.mode;
    const forceLogin = modal.dataset.forceLogin === 'true';
    showAuthModal(currentMode === 'login' ? 'register' : 'login', forceLogin);
}

async function submitAuth() {
    const modal = document.getElementById('auth-modal');
    const mode = modal.dataset.mode;
    const username = document.getElementById('auth-username').value.trim();
    const password = document.getElementById('auth-password').value;
    const nickname = document.getElementById('auth-nickname').value.trim();
    const errorEl = document.getElementById('auth-error');
    const submitBtn = document.getElementById('auth-submit-btn');

    errorEl.style.display = 'none';
    submitBtn.disabled = true;
    submitBtn.textContent = mode === 'login' ? '登录中...' : '注册中...';

    try {
        const url = mode === 'login' ? '/api/auth/login' : '/api/auth/register';
        const body = mode === 'login'
            ? { username, password }
            : { username, password, nickname };

        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || '操作失败');
        }

        authToken = data.token;
        currentUser = data.user;
        localStorage.setItem('auth_token', authToken);
        localStorage.setItem('current_user', JSON.stringify(currentUser));

        updateUserUI();
        document.getElementById('auth-modal').style.display = 'none';
        showToast(mode === 'login' ? '登录成功' : '注册成功', 'success');

        loadStats();
        if (typeof loadTasks === 'function') loadTasks();
        if (typeof loadTodayRecord === 'function') loadTodayRecord();
    } catch (e) {
        errorEl.textContent = e.message;
        errorEl.style.display = 'block';
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = mode === 'login' ? '登录' : '注册';
    }
}

function logout() {
    authToken = null;
    currentUser = null;
    localStorage.removeItem('auth_token');
    localStorage.removeItem('current_user');
    updateUserUI();
    showToast('已退出登录', 'info');
    location.reload();
}

function updateUserUI() {
    const notLogged = document.getElementById('user-not-logged');
    const logged = document.getElementById('user-logged');
    const userName = document.getElementById('user-name');

    if (currentUser) {
        notLogged.style.display = 'none';
        logged.style.display = 'block';
        userName.textContent = currentUser.nickname || currentUser.username;
    } else {
        notLogged.style.display = 'block';
        logged.style.display = 'none';
    }
}

/* ========== 初始化 ========== */
document.addEventListener('DOMContentLoaded', () => {
    initWelcome();
    updateUserUI();

    if (!currentUser) {
        showAuthModal('login', true);
    } else {
        loadStats();
        if (typeof loadTasks === 'function') loadTasks();
        if (typeof loadTodayRecord === 'function') loadTodayRecord();
    }
});
