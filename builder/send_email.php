<?php
header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: POST');
header('Access-Control-Allow-Headers: Content-Type');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit();
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['error' => 'Method not allowed']);
    exit();
}

$input = json_decode(file_get_contents('php://input'), true);

if (!$input) {
    http_response_code(400);
    echo json_encode(['error' => 'Invalid JSON input']);
    exit();
}

$requiredFields = ['first_name', 'last_name', 'email', 'phone_number', 'zip_code'];
foreach ($requiredFields as $field) {
    if (empty($input[$field])) {
        http_response_code(400);
        echo json_encode(['error' => 'Missing required field: ' . $field]);
        exit();
    }
}

if (!filter_var($input['email'], FILTER_VALIDATE_EMAIL)) {
    http_response_code(400);
    echo json_encode(['error' => 'Invalid customer email address']);
    exit();
}

if (empty($input['part_list']) || !is_array($input['part_list'])) {
    $input['part_list'] = [];
}

// Load secure configuration
$config = null;
if (file_exists(__DIR__ . '/config.php')) {
    $config = include __DIR__ . '/config.php';
}

if (file_exists(__DIR__ . '/.env')) {
    // Parse .env file
    $lines = file(__DIR__ . '/.env', FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    if (!$config) {
        $config = ['zeptomail' => [], 'email' => []];
    }
    foreach ($lines as $line) {
        if (strpos($line, '#') === 0) continue; // Skip comments
        if (strpos($line, '=') === false) continue;
        list($key, $value) = explode('=', $line, 2);
        $key = trim($key);
        $value = trim($value, " \t\n\r\0\x0B\"'");
        switch ($key) {
            case 'ZEPTOMAIL_TOKEN':
                $config['zeptomail']['token'] = $value;
                break;
            case 'SALES_EMAIL':
                $config['email']['sales_email'] = $value;
                break;
            case 'QUOTE_DAILY_CAP':
                $config['email']['daily_cap'] = $value;
                break;
        }
    }
}

if (!$config || !isset($config['zeptomail']['token'])) {
    http_response_code(500);
    echo json_encode(['error' => 'Email configuration not found. Please check config.php or .env file.']);
    exit();
}

// Secure configuration
$zeptomailToken = trim($config['zeptomail']['token']);
if (stripos($zeptomailToken, 'Zoho-enczapikey ') !== 0) {
    $zeptomailToken = 'Zoho-enczapikey ' . $zeptomailToken;
}

$salesEmails = parseEmailList($config['email']['sales_email'] ?? 'sales@playmorswingsets.com');
if (empty($salesEmails)) {
    http_response_code(500);
    echo json_encode(['error' => 'Invalid sales email configuration']);
    exit();
}

// Daily send cap. This endpoint is public and unauthenticated, and it delivers
// mail to a caller-supplied CC address, so anyone who finds it can script it.
// The cap does not stop that — it bounds it, keeping a bad day off the
// Zeptomail quota and away from the sending domain's reputation.
//
// Set well above real traffic: a genuine customer should never meet it.
// Override with QUOTE_DAILY_CAP in .env, or email.daily_cap in config.php.
// Set it to 0 to disable the cap entirely.
$dailyCap = $config['email']['daily_cap'] ?? 200;
$dailyCap = is_numeric($dailyCap) ? (int) $dailyCap : 200;
$counterFile = $config['email']['counter_file']
    ?? sys_get_temp_dir() . '/playmor_quote_count.json';

if ($dailyCap > 0 && !recordSendAgainstDailyCap($counterFile, $dailyCap)) {
    error_log('Quote daily cap of ' . $dailyCap . ' reached; refusing send.');
    http_response_code(429);
    echo json_encode([
        'error' => 'We have reached today\'s limit on quote requests. Please email '
            . 'sales@playmorswingsets.com and we will take care of you right away.'
    ]);
    exit();
}

// Generate HTML email content
$htmlContent = "
<html>
<body style=\"font-family: Arial, sans-serif; margin: 40px; color: #333;\">
  <h2 style=\"color: #4CAF50;\">New Quote Request - Yard Designer</h2>
  
  <div style=\"background: #f9f9f9; padding: 20px; border-radius: 8px; margin: 20px 0;\">
    <h3>Customer Information</h3>
    <p><strong>Name:</strong> " . htmlspecialchars($input['first_name']) . " " . htmlspecialchars($input['last_name']) . "</p>
    <p><strong>Email:</strong> " . htmlspecialchars($input['email']) . "</p>
    <p><strong>Phone:</strong> " . htmlspecialchars($input['phone_number']) . "</p>
    <p><strong>Zip Code:</strong> " . htmlspecialchars($input['zip_code']) . "</p>";

if (!empty($input['notes'])) {
    $htmlContent .= "<p><strong>Notes:</strong> " . htmlspecialchars($input['notes']) . "</p>";
}

$htmlContent .= "
  </div>
  
  <div style=\"margin: 20px 0;\">
    <h3>Design Preview</h3>
    <img src=\"cid:design-preview\" style=\"max-width: 100%; height: auto; border: 1px solid #ddd; border-radius: 8px;\" alt=\"Playground Design\" />
  </div>
  
  <div style=\"background: #f0f8f0; padding: 20px; border-radius: 8px;\">
    <h3>Parts List</h3>
    " . generatePartsListHTML($input['part_list']) . "
  </div>
  
  <p style=\"color: #666; font-size: 12px; margin-top: 30px;\">
    This quote was generated automatically from the Yard Designer tool at playmorswingsets.com
  </p>
</body>
</html>";

// Generate text version
$textContent = "Quote Request from " . $input['first_name'] . " " . $input['last_name'] . "\n\n";
$textContent .= "Contact Info:\n";
$textContent .= "Email: " . $input['email'] . "\n";
$textContent .= "Phone: " . $input['phone_number'] . "\n";
$textContent .= "Zip Code: " . $input['zip_code'] . "\n\n";

if (!empty($input['notes'])) {
    $textContent .= "Notes: " . $input['notes'] . "\n\n";
}

$textContent .= "Parts List:\n";
foreach ($input['part_list'] as $part) {
    $textContent .= "• " . $part['name'] . "\n";
    if (!empty($part['options'])) {
        foreach ($part['options'] as $option) {
            $textContent .= "  - " . $option . "\n";
        }
    }
    $textContent .= "\n";
}

// Prepare email payload
$emailPayload = [
    'from' => ['address' => 'sales@playmorswingsets.com'],
    'to' => array_map(function ($address) {
        return [
            'email_address' => [
                'address' => $address,
                'name' => 'Sales Team'
            ]
        ];
    }, $salesEmails),
    'cc' => [[
        'email_address' => [
            'address' => $input['email'],
            'name' => $input['first_name'] . ' ' . $input['last_name']
        ]
    ]],
    'reply_to' => [[
        'address' => $input['email'],
        'name' => $input['first_name'] . ' ' . $input['last_name']
    ]],
    'subject' => 'Quote Request from ' . $input['first_name'] . ' ' . $input['last_name'] . ' - 3D Configurator',
    'htmlbody' => $htmlContent,
    'textbody' => $textContent
];

// Add design preview image as inline attachment for CID reference
if (!empty($input['design_image'])) {
    // Extract base64 data from data URL
    $imageData = $input['design_image'];
    if (strpos($imageData, 'data:image/png;base64,') === 0) {
        $base64Data = substr($imageData, strlen('data:image/png;base64,'));
        $emailPayload['inline_images'] = [[
            'content' => $base64Data,
            'mime_type' => 'image/png',
            'name' => 'design-preview.png',
            'cid' => 'design-preview'
        ]];
    } elseif (strpos($imageData, 'data:image/jpeg;base64,') === 0) {
        $base64Data = substr($imageData, strlen('data:image/jpeg;base64,'));
        $emailPayload['inline_images'] = [[
            'content' => $base64Data,
            'mime_type' => 'image/jpeg',
            'name' => 'design-preview.jpg',
            'cid' => 'design-preview'
        ]];
    }
}

// Add PDF attachment if provided
if (!empty($input['parts_pdf'])) {
    if (!isset($emailPayload['attachments'])) $emailPayload['attachments'] = [];
    $emailPayload['attachments'][] = [
        'content' => $input['parts_pdf'],
        'mime_type' => 'application/pdf',
        'name' => 'quote-' . $input['first_name'] . '-' . $input['last_name'] . '-' . time() . '.pdf'
    ];
}

// Add blueprint JSON attachment if provided
if (!empty($input['blueprint_json'])) {
    if (!isset($emailPayload['attachments'])) $emailPayload['attachments'] = [];
    $blueprintContent = base64_encode($input['blueprint_json']);
    $emailPayload['attachments'][] = [
        'content' => $blueprintContent,
        'mime_type' => 'application/json',
        'name' => 'design-' . $input['first_name'] . '-' . $input['last_name'] . '-' . time() . '.json'
    ];
}

// Send email via Zeptomail
$curl = curl_init();

curl_setopt_array($curl, [
    CURLOPT_URL => 'https://api.zeptomail.com/v1.1/email',
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_ENCODING => '',
    CURLOPT_MAXREDIRS => 10,
    CURLOPT_TIMEOUT => 30,
    CURLOPT_HTTP_VERSION => CURL_HTTP_VERSION_1_1,
    CURLOPT_CUSTOMREQUEST => 'POST',
    CURLOPT_POSTFIELDS => json_encode($emailPayload),
    CURLOPT_HTTPHEADER => [
        'accept: application/json',
        'authorization: ' . $zeptomailToken,
        'cache-control: no-cache',
        'content-type: application/json',
    ],
]);

$response = curl_exec($curl);
$httpCode = curl_getinfo($curl, CURLINFO_HTTP_CODE);
$err = curl_error($curl);

// No curl_close(): a no-op since PHP 8.0 and deprecated in 8.5, where the
// notice prints into the response body and breaks the frontend's JSON.parse,
// turning a successful send into a "quote failed" alert. The handle is freed
// when it goes out of scope.

if ($err) {
    http_response_code(500);
    error_log('Quote email cURL error: ' . $err);
    echo json_encode(['error' => 'cURL Error: ' . $err]);
} elseif ($httpCode < 200 || $httpCode >= 300) {
    error_log('Quote email API error (' . $httpCode . '): ' . $response);
    http_response_code($httpCode);
    $decodedResponse = json_decode($response, true);
    echo json_encode([
        'error' => 'Email API Error',
        'status' => $httpCode,
        'response' => $decodedResponse ?: $response
    ]);
} else {
    echo json_encode(['success' => true, 'message' => 'Email sent successfully', 'status' => $httpCode]);
}

/**
 * Counts one send against today's total and says whether it may proceed.
 *
 * Fails OPEN by design: any problem reading, locking or writing the counter
 * returns true and the quote goes out. A customer has just spent real effort
 * designing a playset, and losing that is worse than letting an abuser past a
 * limiter that is only there to bound damage in the first place.
 *
 * Counts attempts rather than successes, so a script hammering a payload that
 * Zeptomail rejects still burns the day's budget.
 */
function recordSendAgainstDailyCap($file, $cap) {
    $handle = @fopen($file, 'c+');
    if ($handle === false) {
        error_log('Quote cap: cannot open counter ' . $file . '; allowing send.');
        return true;
    }

    if (!flock($handle, LOCK_EX)) {
        fclose($handle);
        error_log('Quote cap: cannot lock counter; allowing send.');
        return true;
    }

    $today = date('Y-m-d');
    $state = json_decode((string) stream_get_contents($handle), true);
    $count = (is_array($state) && isset($state['date']) && $state['date'] === $today)
        ? (int) ($state['count'] ?? 0)
        : 0;

    $allowed = $count < $cap;
    if ($allowed) {
        ftruncate($handle, 0);
        rewind($handle);
        fwrite($handle, json_encode(['date' => $today, 'count' => $count + 1]));
        fflush($handle);
    }

    flock($handle, LOCK_UN);
    fclose($handle);

    return $allowed;
}

function generatePartsListHTML($partList) {
    $html = '<ul style="margin: 10px 0; padding-left: 20px;">';
    foreach ($partList as $part) {
        $html .= '<li style="margin: 8px 0; font-weight: bold;">' . htmlspecialchars($part['name']);
        if (!empty($part['options'])) {
            $html .= '<ul style="margin: 5px 0; padding-left: 20px; font-weight: normal;">';
            foreach ($part['options'] as $option) {
                $html .= '<li style="margin: 3px 0; color: #666;">' . htmlspecialchars($option) . '</li>';
            }
            $html .= '</ul>';
        }
        $html .= '</li>';
    }
    $html .= '</ul>';
    return $html;
}

function parseEmailList($emails) {
    if (is_array($emails)) {
        $emails = implode(',', $emails);
    }

    $addresses = preg_split('/[,\s;]+/', (string) $emails, -1, PREG_SPLIT_NO_EMPTY);
    $validAddresses = [];

    foreach ($addresses as $address) {
        $address = trim($address);
        if (!filter_var($address, FILTER_VALIDATE_EMAIL)) {
            return [];
        }
        $validAddresses[] = $address;
    }

    return array_values(array_unique($validAddresses));
}
?>
