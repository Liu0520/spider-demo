import requests
from bs4 import BeautifulSoup
import os
import time
from PIL import Image # 导入Pillow库
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, WebDriverException

# --- 配置区域 ---
# 目标网站的基础URL (例如: 'https://www.example-comic-site.com')
BASE_URL = 'https://m.kuaikanmanhua.com'
# 漫画的主页面URL或漫画名称，用于构建URL (例如: '/comics/your-comic-name/')
COMIC_PATH_OR_NAME = '/mobile/comics/290202/'
# 要爬取的章节数量
CHAPTERS_TO_SCRAPE = 2
# 保存漫画的根目录
SAVE_DIRECTORY = 'comics_downloaded'
# 请求头，模拟浏览器访问
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
# 下载图片间的延迟（秒），避免过于频繁请求
DOWNLOAD_DELAY = 0.05
# 滚动加载配置
SCROLL_PAUSE_TIME = 2 # 每次滚动后等待加载的时间（秒）
MAX_SCROLL_ATTEMPTS = 10 # 最大滚动次数，防止无限滚动
# 图片拼接配置
MAX_STITCHED_IMAGE_HEIGHT = 60000 # 每张拼接图片的最大高度（像素）

# --- 辅助函数 ---

def fetch_page(url):
    """使用 Selenium 获取动态加载的网页内容"""
    print(f"正在使用 Selenium 获取页面: {url}")
    driver = None
    try:
        # 自动下载和管理 ChromeDriver
        options = webdriver.ChromeOptions()
        options.add_argument('--headless') # 无头模式，不打开浏览器界面
        options.add_argument('--disable-gpu') # 推荐在无头模式下使用
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument(f'user-agent={HEADERS["User-Agent"]}') # 设置User-Agent

        try:
            service = ChromeService(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
        except Exception as e:
            print(f"初始化 ChromeDriver 失败: {e}")
            print("请确保 Chrome 浏览器已安装，并且 ChromeDriver 与之兼容。")
            print("或者，您可以手动下载 ChromeDriver 并将其路径添加到系统 PATH 中，或在脚本中指定其路径。")
            return None

        driver.get(url)
        time.sleep(SCROLL_PAUSE_TIME)  # 初始加载等待

        last_height = driver.execute_script("return document.body.scrollHeight")
        scroll_attempts = 0

        print("开始模拟滚动加载页面...")
        while scroll_attempts < MAX_SCROLL_ATTEMPTS:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(SCROLL_PAUSE_TIME) # 等待页面加载
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                print("页面高度未改变，可能已加载完毕或无更多内容。")
                break
            last_height = new_height
            scroll_attempts += 1
            print(f"滚动尝试 {scroll_attempts}/{MAX_SCROLL_ATTEMPTS}, 页面高度: {new_height}")

        print("页面滚动加载完成。")
        page_source = driver.page_source
        return page_source
    except TimeoutException:
        print(f"加载页面 {url} 超时。")
        return None
    except WebDriverException as e:
        print(f"WebDriver 错误: {e}")
        return None
    except Exception as e:
        print(f"获取页面 {url} 时发生未知错误: {e}")
        return None
    finally:
        if driver:
            driver.quit()
            print("WebDriver 已关闭。")

def download_image(image_url, save_path, chapter_folder, image_name):
    """下载单张图片"""
    try:
        img_response = requests.get(image_url, headers=HEADERS, stream=True, timeout=30)
        img_response.raise_for_status()

        full_save_path = os.path.join(save_path, chapter_folder)
        if not os.path.exists(full_save_path):
            os.makedirs(full_save_path)

        # 获取文件扩展名并去除URL参数
        base_url = image_url.split('.h?')[0]
        file_extension = os.path.splitext(base_url)[1] or '.jpg' # 默认jpg
        # 确保文件名合法
        image_name_cleaned = "".join([c for c in image_name if c.isalnum() or c in (' ', '.', '_')]).rstrip()
        image_filename = os.path.join(full_save_path, f"{image_name_cleaned}{file_extension}")

        with open(image_filename, 'wb') as f:
            for chunk in img_response.iter_content(1024):
                f.write(chunk)
        print(f"图片已保存: {image_filename}")
        time.sleep(DOWNLOAD_DELAY) # 下载间隙
        return True
    except requests.exceptions.RequestException as e:
        print(f"下载图片 {image_url} 失败: {e}")
        return False
    except IOError as e:
        print(f"保存图片 {image_filename} 失败: {e}")
        return False

# --- 辅助函数 ---

def stitch_images_vertically(image_paths, output_dir, base_output_filename, max_height_per_stitch=MAX_STITCHED_IMAGE_HEIGHT):
    """将一系列图片垂直拼接成一张大图"""
    if not image_paths:
        print("没有图片可供拼接。")
        return

    images = []
    total_height = 0
    max_width = 0

    try:
        for img_path in image_paths:
            if not os.path.exists(img_path):
                print(f"警告: 图片文件不存在，跳过拼接: {img_path}")
                continue
            img = Image.open(img_path)
            images.append(img)
            total_height += img.height
            if img.width > max_width:
                max_width = img.width
    except Exception as e:
        print(f"打开图片时出错: {e}")
        # 清理已打开的图片
        for img in images:
            img.close()
        return

    if not images:
        print("没有有效的图片可供拼接。")
        return

    # 将图片分块进行拼接
    image_groups = []
    current_group = []
    current_group_height = 0

    for img_path in image_paths:
        if not os.path.exists(img_path):
            print(f"警告: 图片文件不存在，跳过拼接: {img_path}")
            continue
        try:
            with Image.open(img_path) as img:
                if current_group_height + img.height > max_height_per_stitch and current_group:
                    image_groups.append(current_group)
                    current_group = []
                    current_group_height = 0
                current_group.append(img_path)
                current_group_height += img.height
        except Exception as e:
            print(f"打开图片 {img_path} 时出错: {e}")
            continue # 跳过损坏的图片
    
    if current_group: # 添加最后一组
        image_groups.append(current_group)

    if not image_groups:
        print("没有有效的图片组可供拼接。")
        return

    for i, group_paths in enumerate(image_groups):
        images_in_group = []
        group_total_height = 0
        group_max_width = 0
        valid_images_in_group = True
        try:
            for img_path in group_paths:
                img = Image.open(img_path)
                images_in_group.append(img)
                group_total_height += img.height
                if img.width > group_max_width:
                    group_max_width = img.width
        except Exception as e:
            print(f"在处理第 {i+1} 组图片时打开图片出错: {e}")
            # 清理已打开的图片
            for img_obj in images_in_group:
                img_obj.close()
            valid_images_in_group = False # 标记这组图片无效
            continue # 跳到下一组

        if not images_in_group or not valid_images_in_group:
            print(f"第 {i+1} 组没有有效的图片可供拼接。")
            continue

        stitched_image = Image.new('RGB', (group_max_width, group_total_height))
        current_y = 0
        for img_obj in images_in_group:
            stitched_image.paste(img_obj, (0, current_y))
            current_y += img_obj.height
            img_obj.close() # 关闭单张图片

        # 构建输出路径
        # 获取原始文件名的扩展名，如果拼接多张图片，则默认为 .jpg
        # 这里我们假设所有图片都是同一种类型，或者可以接受输出为 .jpg
        # _, ext = os.path.splitext(group_paths[0]) if group_paths else (None, '.jpg') 
        ext = '.jpg' # 固定输出为jpg
        output_filename = f"{base_output_filename}_{i+1}{ext}"
        final_output_path = os.path.join(output_dir, output_filename)

        try:
            stitched_image.save(final_output_path)
            print(f"拼接后的图片已保存: {final_output_path}")
        except IOError as e:
            print(f"保存拼接图片 {final_output_path} 失败: {e}")
        except ValueError as e: # Pillow 可能会因为图片过大抛出 ValueError
            print(f"保存拼接图片 {final_output_path} 失败 (ValueError): {e}. 图片尺寸可能仍然过大 ({group_max_width}x{group_total_height}).")
        finally:
            stitched_image.close()

# --- 核心爬取逻辑 (需要用户根据目标网站结构进行修改) ---

def get_chapter_links(comic_main_page_url):
    """从漫画主页获取章节链接列表

    你需要根据实际网站的HTML结构修改这里的选择器。
    """
    print(f"正在从 {comic_main_page_url} 获取章节列表...")
    html_content = fetch_page(comic_main_page_url)
    if not html_content:
        return [], None

    soup = BeautifulSoup(html_content, 'html.parser')
    chapter_links = []

    # 根据用户提供的HTML结构，此函数现在提取指定页面中的所有图片链接和标题
    image_list_container = soup.find('div', class_='imgList')
    if image_list_container:
        images_found_count = 0
        for img_tag in image_list_container.find_all('img'):
            image_url = img_tag.get('data-src')
            if not image_url:  # Fallback to src if data-src is not present or empty
                image_url = img_tag.get('src')

            if not image_url:  # Skip if no URL could be found
                # print(f"DEBUG: 跳过一个没有 data-src 或 src 的 img 标签: {img_tag}")
                continue

            image_title = img_tag.get('alt', f'图片_{images_found_count + 1}') # Use alt text or a default title

            # 确保URL是完整的
            if not image_url.startswith('http'):
                from urllib.parse import urljoin # Import locally as in original code
                image_url = urljoin(comic_main_page_url, image_url)
            
            chapter_links.append({'title': image_title, 'url': image_url})
            images_found_count += 1
            print(f"发现图片: {image_title} ({image_url})")

        if images_found_count == 0:
             print(f"警告: 在 'div.imgList' 中找到了容器，但未能提取任何图片链接。请检查 <img> 标签结构和属性 (data-src, src, alt)。")
            
    else:
        print(f"错误: 在 {comic_main_page_url} 未找到 'div.imgList' 容器。请检查页面结构或选择器。")

    # 注意: 此函数现在返回的是图片详情列表。
    # 主调函数可能需要相应调整以正确处理这些“章节”条目作为图片。
    # 示例数据和旧的警告信息已移除，因为函数的核心逻辑已根据用户请求更新。
    return chapter_links, soup # 返回章节字典列表和soup对象



# --- 主执行函数 ---

def main():
    """主执行函数"""
    if not BASE_URL or not COMIC_PATH_OR_NAME:
        print("错误: 请在脚本顶部配置 BASE_URL 和 COMIC_PATH_OR_NAME。")
        return

    # 构建漫画主页URL
    # 假设 COMIC_PATH_OR_NAME 是漫画路径的一部分
    if COMIC_PATH_OR_NAME.startswith('http'):
        comic_main_page_url = COMIC_PATH_OR_NAME
    elif BASE_URL.endswith('/') and COMIC_PATH_OR_NAME.startswith('/'):
        comic_main_page_url = BASE_URL.rstrip('/') + COMIC_PATH_OR_NAME
    elif not BASE_URL.endswith('/') and not COMIC_PATH_OR_NAME.startswith('/'):
        comic_main_page_url = BASE_URL + '/' + COMIC_PATH_OR_NAME
    else:
        comic_main_page_url = BASE_URL + COMIC_PATH_OR_NAME

    print(f"开始爬取漫画: {comic_main_page_url}")
    print(f"计划爬取章节数: {CHAPTERS_TO_SCRAPE}")
    print(f"漫画将保存在: {os.path.abspath(SAVE_DIRECTORY)}")

    # 1. 获取图片链接和页面Soup对象
    all_image_details, soup = get_chapter_links(comic_main_page_url)

    if not all_image_details:
        print("未能获取到任何图片链接，请检查 'get_chapter_links' 函数中的选择器和目标网站。")
        if not soup:
             print("并且未能获取页面Soup对象，无法提取章节标题。")
        return

    # 确定拼接后图片的基础文件名 (章节名)
    chapter_name_for_stitched_file = "DefaultChapter" # 默认值
    if soup:
        page_title_tag = soup.find('title')
        if page_title_tag and page_title_tag.string:
            extracted_title = page_title_tag.string.strip()
            # 清理标题使其成为合法的文件名组件
            sanitized_title = "".join([c for c in extracted_title if c.isalnum() or c in (' ', '.', '_', '-')]).rstrip()
            if sanitized_title: # 如果清理后不为空则使用
                chapter_name_for_stitched_file = sanitized_title
    
    # 如果从标题获取失败或不合适，则回退到基于 COMIC_PATH_OR_NAME 的标识符
    if chapter_name_for_stitched_file == "DefaultChapter" or not chapter_name_for_stitched_file:
        path_based_identifier = os.path.basename(COMIC_PATH_OR_NAME.rstrip('/'))
        # 进一步清理，移除可能的扩展名等，确保是目录名或纯标识符
        path_based_identifier_cleaned = os.path.splitext(path_based_identifier)[0]
        sanitized_path_identifier = "".join([c for c in path_based_identifier_cleaned if c.isalnum() or c in (' ', '.', '_', '-')]).rstrip()
        if sanitized_path_identifier:
            chapter_name_for_stitched_file = sanitized_path_identifier
        
        if not chapter_name_for_stitched_file: # 再次检查以防万一
             chapter_name_for_stitched_file = "DefaultChapter"
    
    print(f"提取到的用于拼接图片文件名的章节名: {chapter_name_for_stitched_file}")

    # Process all images from the fetched page.
    images_to_process = all_image_details

    # 确定保存该“章节”（页面）的文件夹名称
    # (此处的 chapter_save_folder_name 逻辑保持不变，用于创建子目录)
    chapter_page_identifier_for_folder = os.path.basename(COMIC_PATH_OR_NAME.rstrip('/'))
    chapter_save_folder_name = "".join([c for c in chapter_page_identifier_for_folder if c.isalnum() or c in (' ', '.', '_-')]).rstrip()
    if not chapter_save_folder_name: 
        chapter_save_folder_name = "DefaultChapter" 

    print(f"\n--- 开始处理页面: {comic_main_page_url} ---")
    # The full path for storing images of this chapter/page will be os.path.join(SAVE_DIRECTORY, chapter_save_folder_name)
    print(f"将图片保存在: {os.path.join(SAVE_DIRECTORY, chapter_save_folder_name)}")
    print(f"找到 {len(images_to_process)} 张图片。开始下载...")

    downloaded_image_paths = [] # 用于存储成功下载的图片路径
    # 2. 遍历所有获取到的图片信息并下载它们到统一的章节文件夹中
    for img_idx, image_info in enumerate(images_to_process):
        image_url = image_info.get('url')
        # image_title = image_info.get('title', f'Image_{img_idx+1}') # Image title is available if needed for filename logic

        if not image_url:
            print(f"跳过无效的图片信息: {image_info}")
            continue
        
        # Call download_image with:
        # - image_url: The URL of the image to download.
        # - SAVE_DIRECTORY: The root directory where all comics/chapters are saved.
        # - chapter_save_folder_name: The specific folder for the current chapter/page's images.
        # - f"page_{img_idx + 1}": The base name for the image file (e.g., page_1, page_2).
        # Store the path of the downloaded image for stitching
        base_url_for_ext = image_url.split('.h?')[0]
        file_extension_for_stitch = os.path.splitext(base_url_for_ext)[1] or '.jpg'
        image_filename_for_stitch = os.path.join(SAVE_DIRECTORY, chapter_save_folder_name, f"page_{img_idx + 1}{file_extension_for_stitch}")

        if download_image(image_url, SAVE_DIRECTORY, chapter_save_folder_name, f"page_{img_idx + 1}"):
            downloaded_image_paths.append(image_filename_for_stitch)

    print(f"\n页面 {comic_main_page_url} 的所有图片下载完成。")

    # 3. 拼接下载的图片
    if downloaded_image_paths:
        # 拼接后的图片将保存在章节文件夹内
        output_directory_for_stitched = os.path.join(SAVE_DIRECTORY, chapter_save_folder_name)
        base_stitched_filename = chapter_name_for_stitched_file # 使用提取的章节名
        stitch_images_vertically(downloaded_image_paths, output_directory_for_stitched, base_stitched_filename)

        print("\n开始删除已下载的原始小图片...")
        for image_path_to_delete in downloaded_image_paths:
            try:
                if os.path.exists(image_path_to_delete):
                    os.remove(image_path_to_delete)
                    print(f"已删除原始图片: {image_path_to_delete}")
                else:
                    print(f"警告: 原始图片未找到，无法删除: {image_path_to_delete}")
            except OSError as e:
                print(f"删除原始图片 {image_path_to_delete} 失败: {e}")
        print("原始小图片删除完毕。")
    else:
        print("没有成功下载任何图片，无法进行拼接。")
    # Adjusted the final message to reflect that one page (treated as a chapter) and its images are processed.
    print("\n当前页面图片处理完毕。")

if __name__ == '__main__':
    # 提示用户修改脚本
    print("欢迎使用漫画爬虫脚本！")
    print("重要提示: 此脚本现在使用 Selenium 模拟浏览器行为以处理动态加载（懒加载）的页面。")
    print("您可能仍然需要根据目标网站的HTML结构，修改脚本中的 `get_chapter_links` 函数内部的CSS选择器以正确提取图片信息。")
    print("同时，请在脚本顶部配置 `BASE_URL`, `COMIC_PATH_OR_NAME`, 以及 Selenium 相关的滚动参数 `SCROLL_PAUSE_TIME` 和 `MAX_SCROLL_ATTEMPTS`。")
    print("确保您已安装 Chrome 浏览器。脚本将尝试自动下载和管理 ChromeDriver。")
    print("-" * 30)

    # 检查依赖
    try:
        import requests
        from bs4 import BeautifulSoup
        from PIL import Image
        from selenium import webdriver # 检查Selenium
        from webdriver_manager.chrome import ChromeDriverManager # 检查webdriver-manager
    except ImportError:
        print("错误: 缺少必要的库。请安装 'requests', 'beautifulsoup4', 'Pillow', 'selenium', 和 'webdriver-manager'。")
        print("您可以使用以下命令安装: pip install requests beautifulsoup4 Pillow selenium webdriver-manager")
        exit(1)

    main()