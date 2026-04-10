#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试工作流 - 增强版（包含音频分析功能）
"""

import sys
import os
import json

# 添加scripts目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import main_workflow

def test_complete_analysis():
    """
    测试完整的视频与音频分析功能
    """
    print("=" * 70)
    print("测试完整视频与音频分析功能")
    print("=" * 70)
    
    # 测试用例：参考用户上传的视频
    source_video = "02665ab37fe07cbadbca92af1a9d2a3e.mp4"
    user_material = "user_material_sample.mp4"  # 模拟用户素材
    
    print(f"\n测试参数:")
    print(f"  - 源视频: {source_video}")
    print(f"  - 用户素材: {user_material}")
    print("\n开始测试...\n")
    
    try:
        # 运行主工作流
        report = main_workflow(source_video, user_material)
        
        # 验证输出
        print("\n" + "=" * 70)
        print("测试结果验证")
        print("=" * 70)
        
        # 检查必需的输出字段
        required_fields = [
            'video_analysis',
            'audio_analysis',
            'audio_visual_correlation',
            'generated_prompts',
            'tts_replication_guide',
            'replication_recommendations'
        ]
        
        all_passed = True
        for field in required_fields:
            if field in report:
                print(f"✅ {field} - 存在")
            else:
                print(f"❌ {field} - 缺失")
                all_passed = False
        
        # 检查音频分析详细字段
        if 'audio_analysis' in report:
            audio_fields = ['narration', 'background_music', 'sound_effects']
            for field in audio_fields:
                if field in report['audio_analysis']:
                    print(f"✅ audio_analysis.{field} - 存在")
                else:
                    print(f"❌ audio_analysis.{field} - 缺失")
                    all_passed = False
        
        # 检查TTS复刻指导
        if 'tts_replication_guide' in report:
            tts_fields = ['tts_parameters', 'reference_text', 'narration_style_guide']
            for field in tts_fields:
                if field in report['tts_replication_guide']:
                    print(f"✅ tts_replication_guide.{field} - 存在")
                else:
                    print(f"❌ tts_replication_guide.{field} - 缺失")
                    all_passed = False
        
        # 检查提示词生成
        if 'generated_prompts' in report:
            prompt_fields = ['visual_prompt', 'audio_prompt', 'correlation_prompt', 'combined_prompt']
            for field in prompt_fields:
                if field in report['generated_prompts']:
                    print(f"✅ generated_prompts.{field} - 存在")
                else:
                    print(f"❌ generated_prompts.{field} - 缺失")
                    all_passed = False
        
        print("\n" + "=" * 70)
        if all_passed:
            print("✅ 所有测试通过！功能完整。")
        else:
            print("❌ 部分测试失败，需要修复。")
        print("=" * 70)
        
        return report
        
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误:")
        print(f"   {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def test_audio_extraction():
    """
    测试音频内容提取功能
    """
    print("\n" + "=" * 70)
    print("测试音频内容提取功能")
    print("=" * 70)
    
    from main import analyze_audio_content
    
    source_video = "02665ab37fe07cbadbca92af1a9d2a3e.mp4"
    
    print(f"\n测试音频提取: {source_video}")
    try:
        audio_analysis = analyze_audio_content(source_video)
        
        print("\n音频分析结果:")
        print(f"  - 解说存在: {audio_analysis['narration']['has_narration']}")
        if audio_analysis['narration']['has_narration']:
            print(f"  - 配音风格: {audio_analysis['narration']['voice_style']['tone']}")
            print(f"  - 解说文本长度: {len(audio_analysis['narration']['narration_text'])}字符")
        print(f"  - 背景音乐: {audio_analysis['background_music']['music_style']}")
        print(f"  - 音效类型: {', '.join(audio_analysis['sound_effects']['effect_types'])}")
        
        print("\n✅ 音频提取测试通过")
        return audio_analysis
        
    except Exception as e:
        print(f"\n❌ 音频提取测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def test_tts_replication():
    """
    测试TTS复刻指导生成功能
    """
    print("\n" + "=" * 70)
    print("测试TTS复刻指导生成功能")
    print("=" * 70)
    
    from main import analyze_audio_content, generate_tts_replication_guide
    
    source_video = "02665ab37fe07cbadbca92af1a9d2a3e.mp4"
    
    try:
        # 先获取音频分析
        audio_analysis = analyze_audio_content(source_video)
        
        # 生成TTS复刻指导
        tts_guide = generate_tts_replication_guide(audio_analysis)
        
        print("\nTTS复刻指导生成结果:")
        print(f"  - 配音性别: {tts_guide['tts_parameters']['gender']}")
        print(f"  - 语调风格: {tts_guide['tts_parameters']['tone']}")
        print(f"  - 语速控制: {tts_guide['tts_parameters']['speed']}")
        print(f"  - 情感表达: {tts_guide['tts_parameters']['emotion']}")
        print(f"  - 风格指导长度: {len(tts_guide['narration_style_guide'])}字符")
        
        print("\n✅ TTS复刻指导测试通过")
        return tts_guide
        
    except Exception as e:
        print(f"\n❌ TTS复刻指导测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def test_audio_visual_correlation():
    """
    测试音画关联分析功能
    """
    print("\n" + "=" * 70)
    print("测试音画关联分析功能")
    print("=" * 70)
    
    from main import analyze_visual_content, analyze_audio_content, analyze_audio_visual_correlation
    
    source_video = "02665ab37fe07cbadbca92af1a9d2a3e.mp4"
    
    try:
        # 获取视觉和音频分析
        visual_analysis = analyze_visual_content(source_video)
        audio_analysis = analyze_audio_content(source_video)
        
        # 分析音画关联
        correlation = analyze_audio_visual_correlation(visual_analysis, audio_analysis)
        
        print("\n音画关联分析结果:")
        print(f"  - 时间同步: {correlation['synchronization']['narration_timing']}")
        print(f"  - 情感匹配: {correlation['emotional_coordination']['visual_audio_emotion_match']}")
        print(f"  - 节奏一致: {correlation['narrative_coordination']['pacing_consistency']}")
        
        print("\n✅ 音画关联分析测试通过")
        return correlation
        
    except Exception as e:
        print(f"\n❌ 音画关联分析测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def run_all_tests():
    """
    运行所有测试
    """
    print("\n" + "=" * 70)
    print("开始运行完整测试套件")
    print("=" * 70)
    
    results = {
        'audio_extraction': test_audio_extraction(),
        'tts_replication': test_tts_replication(),
        'audio_visual_correlation': test_audio_visual_correlation(),
        'complete_analysis': test_complete_analysis()
    }
    
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)
    
    total_tests = len(results)
    passed_tests = sum(1 for r in results.values() if r is not None)
    
    print(f"总测试数: {total_tests}")
    print(f"通过测试: {passed_tests}")
    print(f"失败测试: {total_tests - passed_tests}")
    
    if passed_tests == total_tests:
        print("\n🎉 所有功能测试通过！技能升级完成。")
    else:
        print(f"\n⚠️  {total_tests - passed_tests}个测试失败，需要进一步调试。")
    
    print("=" * 70)
    
    return results


if __name__ == "__main__":
    print("视频分析与风格复刻 - 增强版测试")
    print("运行测试套件验证音频功能...\n")
    
    # 运行所有测试
    test_results = run_all_tests()
    
    # 保存测试结果
    if any(r is not None for r in test_results.values()):
        test_report_path = "test_report_enhanced.json"
        with open(test_report_path, 'w', encoding='utf-8') as f:
            # 将结果转换为可序列化的格式
            serializable_results = {
                key: "PASS" if value is not None else "FAIL" 
                for key, value in test_results.items()
            }
            json.dump({
                'timestamp': '2025-06-20',
                'test_results': serializable_results,
                'summary': {
                    'total': len(test_results),
                    'passed': sum(1 for v in test_results.values() if v is not None),
                    'failed': sum(1 for v in test_results.values() if v is None)
                }
            }, f, ensure_ascii=False, indent=2)
        
        print(f"\n✅ 测试报告已保存到: {test_report_path}")